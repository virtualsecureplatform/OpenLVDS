#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Actual paired SKY130 gates with local taps and one public output per macro.

Use native GDS and exact LEF local-interconnect access shapes. Keep every
failed placement. Geometry/connectivity alone never qualifies delay or load.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import layout
import inspect_mim_switch_pcells_v2 as environment
import dcc_balanced_xnor_v2 as topology
import restrict_macro_rails_v4 as access

ROOT=layout.ROOT
VERSION='native-swapped-input-xnor-compound-physical-v2.1'
TAP='sky130_fd_sc_hd__tapvpwrvgnd_1'
sha=environment.sha


def default_plan():
    return dict(signal_y=[.8,1.45,2.1],signal_width=.28,ground_y=0.,power_y=2.92,
        power_width=.6,drop_width=.18)


def lef_cell(text,name):
    matches=re.findall(r'(?ms)^MACRO '+re.escape(name)+r'\s*\n(.*?)^END '+re.escape(name)+r'\s*$',text)
    if len(matches)!=1:raise ValueError('Missing/duplicate native LEF cell: '+name)
    size=re.search(r'\bSIZE\s+([0-9.]+)\s+BY\s+([0-9.]+)',matches[0])
    pins={m[1]:access.geometry.rectangles(m[2]) for m in access.geometry.PIN.finditer(matches[0])}
    if size is None:raise ValueError('Native LEF size missing')
    return dict(width=float(size[1]),height=float(size[2]),pins=pins)


def signal_point(shapes):
    candidates=[r for layer,r in shapes if layer=='li1' and r[2]-r[0]>=.17 and r[3]-r[1]>=.17]
    if not candidates:raise ValueError('No native LI1 contact access')
    r=max(candidates,key=lambda r:(r[2]-r[0])*(r[3]-r[1]))
    return tuple(round((r[i]+r[i+2])/2/layout.GRID)*layout.GRID for i in [0,1])


def cell_definition(text,name):
    blocks=re.findall(r'(?ims)^\.subckt\s+'+re.escape(name)+r'\s[^\n]*\n.*?^\.ends[^\n]*',text)
    if len(blocks)!=1:raise ValueError('Missing native transistor definition: '+name)
    return blocks[0]+'\n'


def source_schematic(model,library):
    macro=topology.COMPOUNDS[model];inputs,output=topology.SIGNALS[model]
    ports=[*inputs,output,'VPWR','VGND']
    gate=cell_definition(library,model);tap=cell_definition(library,TAP)
    gate_order=gate.splitlines()[0].split()[2:];tap_order=tap.splitlines()[0].split()[2:]
    nets=dict(VNB='VGND',VPB='VPWR',VPWR='VPWR',VGND='VGND',**{p:p for p in [*inputs,output]})
    text=gate+'\n'+tap+'\n.subckt '+macro+' '+' '.join(ports)+'\n'
    for i in [0,1]:text+='Xgate'+str(i)+' '+' '.join(nets[topology.swapped_pin(i,p)] for p in gate_order)+' '+model+'\n'
    for suffix in ['left','right']:text+='Xtap_'+suffix+' '+' '.join(nets[p] for p in tap_order)+' '+TAP+'\n'
    return text+'.ends '+macro+'\n'


def prepare(plan):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    files=[pdk/'libs.ref/sky130_fd_sc_hd'/n for n in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds','spice/sky130_fd_sc_hd.spice']]
    files += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=[Path(__file__),Path(layout.__file__),Path(environment.__file__),Path(topology.__file__),
        Path(topology.native.__file__),Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):sha(p) for p in code},
        pdk_files={str(p):sha(p) for p in files},tools=environment.tools(),configuration=plan)
    out=ROOT/'build/diagnostics/balanced_xnor_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/balanced_xnor_physical_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in i['code'].items()) or any(sha(Path(n))!=v for n,v in i['pdk_files'].items())
        or environment.tools()!=i['tools']):raise ValueError('Compound driver inputs changed')
    return m


def native_bbox(path):
    # Native GDS imports may use sticky rlabels ("rlabel layer s ...").
    # Bounding boxes need only actual mask rectangles, not label syntax.
    rects=[list(map(int,line.split()[1:])) for line in path.read_text().splitlines() if line.startswith('rect ')]
    if not rects or any(len(r)!=4 for r in rects):raise ValueError('Missing or invalid native cell rectangles')
    return [min(r[0] for r in rects)*layout.GRID,min(r[1] for r in rects)*layout.GRID,
            max(r[2] for r in rects)*layout.GRID,max(r[3] for r in rects)*layout.GRID]


def draw(out,model,lef,library,gds,plan):
    macro=topology.COMPOUNDS[model];inputs,output=topology.SIGNALS[model]
    gate=lef_cell(lef,model);tap=lef_cell(lef,TAP)
    if gate['height']!=tap['height']:raise ValueError('Native row heights differ')
    # Import actual masks, never maglef abstractions. Save only used native cells.
    layout.invoke_magic(out,f'gds readonly false\ngds read {{{gds}}}\nload {model} -silent\nsave {{{out/model}}}\nload {TAP} -silent\nsave {{{out/TAP}}}', 'native_cells')
    boxes={n:native_bbox(out/(n+'.mag')) for n in [model,TAP]}
    width=2*tap['width']+2*gate['width'];starts=[tap['width'],tap['width']+gate['width']]
    g=layout.Geometry();ports={}
    for index,pin in enumerate([*inputs,output]):
        y=plan['signal_y'][index]
        for copy,start in enumerate(starts):
            px,py=signal_point(gate['pins'][topology.swapped_pin(copy,pin)])
            x=start+px
            g.pad('viali',x,py,.17);g.pad('metal1',x,py,.4);g.via12(x,py)
            g.wire('metal2',x,py,x,y,plan['drop_width']);g.via23(x,y)
        g.wire('metal3',.3,y,width-.3,y,plan['signal_width'])
        ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=plan['signal_width'])
    for pin,y,source_y in [('VGND',plan['ground_y'],0.),('VPWR',plan['power_y'],gate['height'])]:
        for x in [tap['width']/2,width-tap['width']/2]:
            g.via12(x,source_y);g.wire('metal2',x,source_y,x,y,plan['drop_width']);g.via23(x,y)
        g.wire('metal3',.3,y,width-.3,y,plan['power_width'])
        ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=plan['power_width'])
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():
        lines.append(f'<< {layer} >>');lines.extend('rect '+' '.join(map(str,r)) for r in rects)
    placement=[(TAP,'tap_left',0.),(model,'gate0',starts[0]),(model,'gate1',starts[1]),(TAP,'tap_right',width-tap['width'])]
    for cell,instance,x in placement:
        lines += [f'use {cell} {instance}','timestamp 0',f'transform 1 0 {round(x/layout.GRID)} 0 1 0',
            'box '+' '.join(str(round(v/layout.GRID)) for v in boxes[cell])]
    lines.append('<< labels >>')
    for index,(pin,p) in enumerate(ports.items(),1):
        x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}',f'port {index} nsew']
    lines.append('<< end >>');(out/(macro+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(macro+'.sch.spice')).write_text(source_schematic(model,library))
    result=layout.qualify(out,macro);raw=out/(macro+'.raw.lef');raw.write_bytes((out/(macro+'.lef')).read_bytes())
    types={p:('INPUT','SIGNAL') for p in inputs};types.update({output:('OUTPUT','SIGNAL'),'VPWR':('INOUT','POWER'),'VGND':('INOUT','GROUND')})
    restricted,view=access.restrict(raw.read_text(),ports,types);(out/(macro+'.lef')).write_text(restricted)
    return dict(result,model=model,macro=macro,ports=ports,integration_pins=view,gds_sha256=sha(out/(macro+'.gds')),
        lef_sha256=sha(out/(macro+'.lef')),raw_lef_sha256=sha(raw),native_cell_sha256={n:sha(out/(n+'.mag')) for n in boxes},
        qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior compound placement')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd'
        lef=(pdk/'lef/sky130_fd_sc_hd.lef').read_text();library=(pdk/'spice/sky130_fd_sc_hd.spice').read_text();rows=[]
        for model in topology.COMPOUNDS:
            folder=out/topology.COMPOUNDS[model];folder.mkdir()
            result=draw(folder,model,lef,library,pdk/'gds/sky130_fd_sc_hd.gds',m['identity']['configuration'])
            (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n');rows.append(result)
        bound(out);result=dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,electrical_qualification_passed=False,
            scope='One swapped-input native XNOR compound geometry/connectivity only; no RC, DCC or timing admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='compound_physical_complete',passed=result['passed'],qualified_phy=False))+'\n')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',nargs='?',type=Path)
    p.add_argument('--plan',type=Path);a=p.parse_args()
    if a.action in ['prepare','campaign']:out=prepare(json.loads(a.plan.read_text()) if a.plan else default_plan());print(out,flush=True)
    elif a.artifact is None:p.error('Provide prepared context')
    else:out=a.artifact.resolve()
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
