#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the actual shared 4x4 MIM shunt before full-bank assembly.

Retain raw and restricted-access LEFs, actual PCell geometry and DRC/LVS.
No ideal capacitor, active selection or electrical admission is supplied.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import layout
import inspect_mim_switch_pcells_v2 as environment
import mim_base_4x4_v2 as unit
import restrict_macro_rails_v2 as access

ROOT=layout.ROOT
NAME=unit.NAME
VERSION='shared-4x4-mim-physical-prototype-v2.1'
sha=environment.sha


def default_plan():
    return dict(center=[4.,3.],escape_y=7.1,right=8.5,node_y=7.1,ground_y=8.2)


def prepare(plan):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    paths=[Path(__file__),Path(unit.__file__),Path(layout.__file__),Path(environment.__file__),
        Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py',
        ROOT/'requirements.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    pdk_files=[pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):sha(p) for p in paths},configuration=plan,
        pdk_files={str(p):sha(p) for p in pdk_files},tools=environment.tools())
    out=ROOT/'build/diagnostics/mim_base_4x4_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/mim_base_4x4_physical_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in i['code'].items())
        or any(sha(Path(n))!=v for n,v in i['pdk_files'].items()) or environment.tools()!=i['tools']):
        raise ValueError('Shared MIM physical inputs changed')
    return m


def run(out):
    m=bound(out);plan=m['identity']['configuration']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior shared-MIM execution')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        cell='base_mim_4x4'
        layout.invoke_magic(out,f'''load {cell} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w 4
dict set p l 4
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {cell}
''','pcell')
        geometry=layout.pcell_info(out/(cell+'.mag'));cx,cy=plan['center']
        pins={n:(layer,cx+x,cy+y) for n,(layer,x,y) in geometry['ports'].items()}
        g=layout.Geometry();_,x,y=pins['C1'];escape=plan['escape_y'];right=plan['right']
        g.wire('metal4',x,y,x,escape,.6);g.via34(x,escape)
        g.wire('metal3',x,escape,x,plan['node_y'],.4)
        g.wire('metal3',.3,plan['node_y'],right,plan['node_y'],.4)
        _,x,y=pins['C2'];g.wire('metal3',x,y,right,y,.4);g.via23(right,y)
        g.wire('metal2',right,y,right,plan['ground_y'],.18);g.via23(right,plan['ground_y'])
        g.wire('metal3',.3,plan['ground_y'],right,plan['ground_y'],.6)
        ports=dict(NODE=dict(layer='metal3',x_um=.3,y_um=plan['node_y'],width_um=.4),
                   VSS=dict(layer='metal3',x_um=.3,y_um=plan['ground_y'],width_um=.6))
        lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
        for layer,rects in g.layers.items():
            lines.append(f'<< {layer} >>');lines.extend('rect '+' '.join(map(str,r)) for r in rects)
        bb=[round(v/layout.GRID) for v in geometry['bbox']]
        lines += [f'use {cell} I0','timestamp 0',f'transform 1 0 {round(cx/layout.GRID)} 0 1 {round(cy/layout.GRID)}',
                  'box '+' '.join(map(str,bb)),'<< labels >>']
        for i,(name,p) in enumerate(ports.items(),1):
            x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
            lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {name}',f'port {i} nsew']
        lines.append('<< end >>');(out/(NAME+'.mag')).write_text('\n'.join(lines)+'\n')
        p,devices=layout.flatten(layout.circuits(unit.schematic()),NAME)
        (out/(NAME+'.sch.spice')).write_text(layout.schematic_text(NAME,p,devices))
        result=layout.qualify(out,NAME);raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
        lef,view=access.restrict(raw.read_text(),ports,dict(NODE=('INPUT','SIGNAL'),VSS=('INOUT','GROUND')))
        (out/(NAME+'.lef')).write_text(lef);bound(out)
        result.update(ports=ports,primitive_geometry=geometry,primitive_sha256=sha(out/(cell+'.mag')),
            gds_sha256=sha(out/(NAME+'.gds')),lef_sha256=sha(out/(NAME+'.lef')),raw_lef_sha256=sha(raw),
            integration_pins=view,qualified_phy=False,electrical_qualification_passed=False,
            scope='Native shared-MIM geometry, Magic DRC/LVS and restricted access only; no bank or timing admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='shared_mim_physical_complete',passed=result['passed'],qualified_phy=False))+'\n')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',nargs='?',type=Path)
    p.add_argument('--plan',type=Path);a=p.parse_args()
    if a.action in ['prepare','campaign']:out=prepare(json.loads(a.plan.read_text()) if a.plan else default_plan());print(out,flush=True)
    elif a.artifact is None:p.error('Provide the prepared context')
    else:out=a.artifact.resolve()
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
