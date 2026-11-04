#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Physically join two actual stack-guard/body-tap NAND2B cells.

Keep the original native GDS and private guards intact. A real shared M4 bus
connects each public net, giving implementation tools one output per macro.
Geometry/LVS is not electrical or whole-controller admission.
"""
import argparse
import fcntl
import hashlib
import json
import re
from pathlib import Path
import layout
import build_nand2b_stack_guard_v2 as single
import build_compound_drivers_v3 as native
import restrict_macro_rails_v5 as abstract

ROOT=layout.ROOT
VERSION='native-stack-guard-nand2b-physical-pair-v2.2'
CONTEXT='nand2b_guard_pair_physical_v2'
CHILD='openlvds_nand2b_4_o1_stack_guard_bodytap_v2'
NAME='openlvds_nand2b_4_o1_stack_guard_pair_v2'
PORTS=['A_N','B','Y','VGND','VPWR']
sha=native.sha


def default_plan():
    return dict(offset_x_um=4.,offset_y_um=5.,gap_um=6.,signal_width_um=.3,
                signal_via_cut_um=.32,signal_via_pad_um=.44,power_width_um=.8,
                signal_first_landing_x_um=10.,signal_landing_pitch_um=3.)


def schematic(text):
    lines=[line.split() for line in text.splitlines() if line.lower().startswith('.subckt '+CHILD+' ')]
    if len(lines)!=1 or set(lines[0][2:])!=set(PORTS):raise ValueError('Guarded child source interface changed')
    rows=[text.rstrip(),'.subckt '+NAME+' '+' '.join(PORTS)]
    for tag in ['left','right']:rows.append('X'+tag+' '+' '.join(lines[0][2:])+' '+CHILD)
    return '\n'.join(rows+['.ends '+NAME,''])


def parent_row(parent):
    m=single.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['passed']:raise ValueError('Require complete clean original guarded geometry')
    rows=[row for row in r['rows'] if row['macro']==CHILD]
    if len(rows)!=1:raise ValueError('Missing exact guarded child')
    row=rows[0];folder=parent/CHILD
    if (row['drc_count']!='0' or not row['lvs_passed'] or not row['passed']
        or sha(folder/(CHILD+'.gds'))!=row['gds_sha256'] or sha(folder/(CHILD+'.lef'))!=row['lef_sha256']
        or sha(folder/(CHILD+'.sch.spice'))!=row['lvs_source_sha256']):raise ValueError('Guarded child geometry/source changed')
    return m,row,folder


def prepare(parent,plan):
    m,_,folder=parent_row(parent)
    if set(plan)!=set(default_plan()) or any(not isinstance(v,(float,int)) or v<=0 for v in plan.values()):raise ValueError('Invalid explicit pair placement')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]+[folder/(CHILD+n) for n in ['.gds','.lef','.sch.spice','.lvs.log','.drc_count.txt']]
    code=[Path(__file__),Path(single.__file__),Path(native.__file__),Path(layout.__file__),Path(abstract.__file__),Path(abstract.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),child=CHILD,configuration=plan,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
        pdk_files=m['identity']['pdk_files'],tools=native.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):raise ValueError('Native guard-pair context changed')
    parent_row(ROOT/i['parent']);return m


def draw(out,child,row,plan):
    source=(child/(CHILD+'.sch.spice')).read_text();lef=(child/(CHILD+'.lef')).read_text()
    cell=native.lef_cell(lef,CHILD);origin=re.search(r'\bORIGIN\s+([-0-9.]+)\s+([-0-9.]+)',lef)
    if origin is None:raise ValueError('Guarded child LEF origin missing')
    ox,oy=map(float,origin.groups());box=[-ox,-oy,cell['width']-ox,cell['height']-oy]
    names=[CHILD,'sky130_fd_sc_hd__nand2b_4','sky130_fd_sc_hd__tapvpwrvgnd_1','clock_mim_1x1_v2','clock_mim_2x2_v2']
    commands=[f'gds readonly false',f'gds read {{{child/(CHILD+".gds")}}}']
    for name in names:commands += [f'load {name} -silent',f'save {{{out/name}}}']
    layout.invoke_magic(out,'\n'.join(commands),'child_import')
    positions=[plan['offset_x_um'],plan['offset_x_um']+cell['width']+plan['gap_um']];yoff=plan['offset_y_um']
    g=layout.Geometry();ports={};left=.3;right=positions[-1]+box[2]+.5
    for number,pin in enumerate(PORTS):
        p=row['ports'][pin]
        if p['layer']!='metal3':raise ValueError('Guarded child public access layer changed')
        y=yoff+p['y_um'];power=pin in ['VGND','VPWR'];width=plan['power_width_um'] if power else plan['signal_width_um']
        # Stagger compact signal vias along the existing M3 public rails.
        # Native rail pitch cannot accommodate the generic larger via landing.
        local_x=plan['signal_first_landing_x_um']+plan['signal_landing_pitch_um']*number if not power else .3
        if not any(layer=='met3' and r[0]<=local_x<=r[2] and r[1]<=p['y_um']<=r[3] for layer,r in cell['pins'][pin]):
            raise ValueError('Pair landing is outside proven public M3 metal')
        for start in positions:
            x=start+local_x
            if power:g.via34(x,y)
            else:
                g.pad('metal3',x,y,plan['signal_via_pad_um']);g.pad('via3',x,y,plan['signal_via_cut_um']);g.pad('metal4',x,y,plan['signal_via_pad_um'])
        g.wire('metal4',left,y,right,y,width)
        ports[pin]=dict(layer='metal4',x_um=left,y_um=y,width_um=width)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    for tag,x in zip(['left','right'],positions):
        lines += [f'use {CHILD} {tag}','timestamp 0',f'transform 1 0 {round(x/layout.GRID)} 0 1 {round(yoff/layout.GRID)}',
                  'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines.append('<< labels >>')
    for n,(pin,p) in enumerate(ports.items(),1):
        x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal4 {x} {y} {x} {y} 0 {pin}',f'port {n} nsew']
    lines.append('<< end >>');(out/(NAME+'.mag')).write_text('\n'.join(lines)+'\n');(out/(NAME+'.sch.spice')).write_text(schematic(source))
    result=layout.qualify(out,NAME);raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    types={p:('OUTPUT' if p=='Y' else 'INPUT','SIGNAL') for p in ['A_N','B','Y']};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    restricted,view=abstract.restrict(raw.read_text(),ports,types);(out/(NAME+'.lef')).write_text(restricted)
    return dict(result,macro=NAME,child=CHILD,child_instances=2,ports=ports,integration_pins=view,
                placement=dict(x_um=positions,y_um=yoff,child_bbox_um=box),gds_sha256=sha(out/(NAME+'.gds')),
                lef_sha256=sha(out/(NAME+'.lef')),qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out);_,row,child=parent_row(ROOT/m['identity']['parent'])
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native pair layout')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        folder=out/NAME;folder.mkdir();result=draw(folder,child,row,m['identity']['configuration']);(folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        bound(out);report=dict(rows=[result],passed=result['passed'],qualified_phy=False,electrical_qualification_passed=False,
            scope='Actual guarded cell pair and shared public M4 wiring, DRC/LVS only; no fresh RC timing, whole-controller or PHY admission')
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=report['passed'],qualified_phy=False))+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--plan',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out,json.loads(a.plan.read_text()) if a.plan else default_plan());print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
