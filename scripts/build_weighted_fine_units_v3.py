#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build actual PDK geometry and DRC/LVS for all five root fine-load cells.

Primitive dimensions are exactly the existing source geometry. Larger plates
are placed from actual PCell bounds; native bodies and all five ports remain.
This is physical fine-cell work, not full-bank timing or PHY admission.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import layout
import weighted_fine_unit_v2 as unit
import weighted_fine_unit_layout_v3 as routing
import build_compound_drivers_v3 as environment
import restrict_macro_rails_v6 as access

ROOT=layout.ROOT
VERSION='five-root-weighted-fine-native-physical-v2.2'
CONTEXT='weighted_fine_unit_physical_v2'
sha=environment.sha


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';tech=pdk/'libs.tech/magic'
    pdks=[tech/'sky130A.magicrc',tech/'sky130A.tech',pdk/'libs.tech/netgen/sky130A_setup.tcl']+sorted(tech.rglob('*.tcl'))
    code=[Path(__file__),Path(unit.__file__),Path(unit.fine.__file__),Path(routing.__file__),Path(layout.__file__),Path(environment.__file__),Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py',ROOT/'build/apptainer/openlvds.sif.sha256']
    identity=dict(version=VERSION,schematics={unit.name(b):hashlib.sha256(unit.schematic(b).encode()).hexdigest() for b in range(5)},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files={str(p):sha(p) for p in pdks},tools=environment.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['code'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or environment.environment.tools()!=i['tools']
        or i['schematics']!={unit.name(b):hashlib.sha256(unit.schematic(b).encode()).hexdigest() for b in range(5)}):raise ValueError('Weighted fine physical context changed')
    return m


def primitives(folder,bit):
    ports,devices=layout.flatten(layout.circuits(unit.schematic(bit)),unit.name(bit));keys=sorted({layout.primitive_key(d) for d in devices});commands=[];names={}
    if ports!=unit.PORTS or len(devices)!=5:raise ValueError('Fine topology changed')
    for model,w,l in keys:
        name='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];names[(model,w,l)]=name
        commands += [f'load {name} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',f'dict set p w {w}',f'dict set p l {l}']
        if 'fet_' in model:commands.append('dict set p botc 0')
        commands += [f'sky130::{model}_draw $p',f'save {name}']
    layout.invoke_magic(folder,'\n'.join(commands),'native_pcells')
    library={k:(name,layout.pcell_info(folder/(name+'.mag'))) for k,name in names.items()}
    record=[dict(model=k[0],width_um=k[1],length_um=k[2],cell=name,geometry=library[k][1],sha256=sha(folder/(name+'.mag'))) for k,name in names.items()]
    (folder/'primitive_geometry.json').write_text(json.dumps(dict(devices=devices,library=record),indent=2)+'\n');return library,devices


def plan(library,devices):
    boxes=[library[layout.primitive_key(d)][1]['bbox'] for d in devices]
    mos=[[3.,4.],[11.,4.],[19.,4.]];target=mos[0][0]+.8
    c0=[target+2.5-boxes[3][0],20.-boxes[3][1]];right=c0[0]+boxes[3][2]
    c1=[right+5.-boxes[4][0],20.-boxes[4][1]]
    highest=max(c0[1]+boxes[3][3],c1[1]+boxes[4][3],*[p[1]+box[3] for p,box in zip(mos,boxes[:3])]);escape=highest+2.
    buses={n:escape+3.4+1.4*i for i,n in enumerate(['NODE','CAP','EN','ENB','VDD','VSS'])}
    low=right+1.5;high=c1[0]+boxes[4][0]-1.5
    ground_columns=[mos[0][0]-1.5,mos[2][0]-1.5,mos[2][0]+.8]
    shared=[x for x in ground_columns if low<=x<=high]
    bottom=shared[0] if shared else (low+high)/2
    columns=[x+dx for x,_ in mos for dx in [-1.5,-.8,0.,.8]]
    if any(abs(bottom-x)<.5 and abs(bottom-x)>layout.GRID/2 for x in columns):raise ValueError('Bottom-plate drop crowds an existing MOS column')
    return dict(mos_centers=mos,cap_centers=[c0,c1],tracks=dict(B=-1.5,D=-.8,G=0.,S=.8),gate_escape=.3,
        cap_escape_y=[escape,escape+1.4],bottom_via_x=[bottom,c1[0]+boxes[4][2]+2.],buses=buses,bus_left=.3,
        bus_right=c1[0]+boxes[4][2]+4.,signal_width=.4,power_width=.6,drop_width=.18)


def run(out):
    bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior weighted fine geometry')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n');rows=[]
        try:
            for bit in range(5):
                name=unit.name(bit);folder=out/name;folder.mkdir();library,devices=primitives(folder,bit);configuration=plan(library,devices)
                cell=SimpleNamespace(NAME=name,schematic=lambda bit=bit:unit.schematic(bit))
                result=routing.draw(folder,library,configuration,cell);result.update(layout.qualify(folder,name))
                raw=folder/(name+'.raw.lef');raw.write_bytes((folder/(name+'.lef')).read_bytes())
                types=dict(NODE=('INPUT','SIGNAL'),EN=('INPUT','SIGNAL'),ENB=('INPUT','SIGNAL'),VDD=('INOUT','POWER'),VSS=('INOUT','GROUND'))
                text,pins=access.restrict(raw.read_text(),result['ports'],types);(folder/(name+'.lef')).write_text(text)
                result.update(macro=name,bit=bit,integration_pins=pins,gds_sha256=sha(folder/(name+'.gds')),lef_sha256=sha(folder/(name+'.lef')),qualified_phy=False,electrical_qualification_passed=False)
                rows.append(result);(folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            bound(out);report=dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,electrical_qualification_passed=False,
                scope='All five actual root-weighted fine cells, native primitive inspection/route/DRC/LVS only; no fresh RC, native timing, bank ROM or PHY admission')
            (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=report['passed'],qualified_phy=False))+'\n');return report
        except Exception as e:
            (out/'state.json').write_text(json.dumps(dict(status='physical_exception',error=str(e),qualified_phy=False))+'\n');raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action in ['prepare','campaign']:out=prepare();print(out,flush=True)
    elif a.artifact is None:p.error('Provide physical artifact')
    else:out=a.artifact.resolve()
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
