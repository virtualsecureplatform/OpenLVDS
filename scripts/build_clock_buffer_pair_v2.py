#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join two unchanged shunted BUF8 cells with real common signal/power rails.

Preserve both native device/private-shunt hierarchies. This implements the
proposed parallel drive geometrically, without claiming its timing fix passes.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import layout
import build_clock_cell_shunts_v4 as single
import build_compound_drivers_v3 as native
import restrict_macro_rails_v5 as abstract

ROOT=layout.ROOT
VERSION='native-two-shunted-buf8-shared-metal4-pair-v2.1'
CONTEXT='clock_buffer_pair_physical_v2'
CHILD='openlvds_buf_8_o4_shunted_v2'
NAME='openlvds_buf_8_o4_shunted_pair_v2'
PORTS=['A','X','VGND','VPWR']
sha=native.sha


def default_plan():return dict(offset_x_um=4.,offset_y_um=5.,gap_um=6.,signal_width_um=.3,
    via_cut_um=.32,via_pad_um=.44,power_width_um=1.6,first_landing_x_um=10.,landing_pitch_um=3.)


def schematic(text):
    headers=re.findall(r'(?im)^\.subckt '+re.escape(CHILD)+r' ([^\n]+)',text)
    if len(headers)!=1 or len(headers[0].split())!=len(PORTS) or set(headers[0].split())!=set(PORTS):raise ValueError('Native BUF8 child interface changed')
    return '\n'.join([text.rstrip(),'.subckt '+NAME+' '+' '.join(PORTS),
        *['X'+tag+' '+headers[0]+' '+CHILD for tag in ['left','right']],'.ends '+NAME,''])


def parent_row(parent):
    m=single.bound(parent);r=json.loads((parent/'summary.json').read_text())
    rows=[v for v in r['rows'] if v['macro']==CHILD]
    if not r['passed'] or len(rows)!=1:raise ValueError('Require clean exact BUF8_o4 native physical family')
    row=rows[0];folder=parent/CHILD
    if (row['drc_count']!='0' or not row['lvs_passed'] or not row['passed']
        or sha(folder/(CHILD+'.gds'))!=row['gds_sha256'] or sha(folder/(CHILD+'.lef'))!=row['lef_sha256']
        or sha(folder/(CHILD+'.sch.spice'))!=row['lvs_source_sha256']):raise ValueError('Native BUF8 physical/source witness changed')
    return m,row,folder


def prepare(parent,plan):
    m,_,child=parent_row(parent)
    if set(plan)!=set(default_plan()) or any(not isinstance(v,(int,float)) or v<=0 for v in plan.values()):
        raise ValueError('Invalid explicit native clock-pair placement')
    files=[parent/n for n in ['manifest.json','summary.json','state.json']]
    files += [child/(CHILD+s) for s in ['.gds','.lef','.sch.spice','.lvs.log','.drc_count.txt']]
    code=[Path(__file__),Path(single.__file__),Path(native.__file__),Path(layout.__file__),Path(abstract.__file__),
          Path(abstract.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),child=CHILD,configuration=plan,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files+code},pdk_files=m['identity']['pdk_files'],tools=native.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):
        raise ValueError('Native parallel clock-buffer physical context changed')
    parent_row(ROOT/i['parent']);return m


def draw(folder,child,row,plan):
    lef=(child/(CHILD+'.lef')).read_text();cell=native.lef_cell(lef,CHILD)
    origin=re.search(r'\bORIGIN\s+([-0-9.]+)\s+([-0-9.]+)',lef)
    if origin is None:raise ValueError('Missing actual native child origin')
    ox,oy=map(float,origin.groups());box=[-ox,-oy,cell['width']-ox,cell['height']-oy]
    names=[CHILD,'sky130_fd_sc_hd__buf_8','sky130_fd_sc_hd__tapvpwrvgnd_1','clock_mim_2x2_v2','clock_mim_4x4_v2']
    commands=[f'gds readonly false',f'gds read {{{child/(CHILD+".gds")}}}']
    for n in names:commands += [f'load {n} -silent',f'save {{{folder/n}}}']
    layout.invoke_magic(folder,'\n'.join(commands),'child_import')
    xs=[plan['offset_x_um'],plan['offset_x_um']+cell['width']+plan['gap_um']];dy=plan['offset_y_um']
    g=layout.Geometry();ports={};left=.3;right=xs[-1]+box[2]+.5
    for index,pin in enumerate(PORTS):
        access=row['ports'][pin]
        if access['layer']!='metal3':raise ValueError('Native public access layer changed')
        local_x=plan['first_landing_x_um']+index*plan['landing_pitch_um'];y=access['y_um'];half=plan['via_pad_um']/2
        if not any(layer=='met3' and r[0]<=local_x-half and r[2]>=local_x+half and r[1]<=y-half and r[3]>=y+half
                   for layer,r in cell['pins'][pin]):
            # Signal M3 rails are 0.32 um tall; a legal landing adds the same
            # 0.44 um pad used by the native guarded-pair routing primitive.
            if pin in ['VGND','VPWR'] or not any(layer=='met3' and r[0]<=local_x-half and r[2]>=local_x+half and r[1]<=y<=r[3]
                                                 for layer,r in cell['pins'][pin]):
                raise ValueError('Clock-pair landing is outside the native public rail')
        y+=dy;width=plan['power_width_um'] if pin in ['VGND','VPWR'] else plan['signal_width_um']
        for x in xs:
            g.pad('metal3',x+local_x,y,plan['via_pad_um']);g.pad('via3',x+local_x,y,plan['via_cut_um']);g.pad('metal4',x+local_x,y,plan['via_pad_um'])
        if pin in ['VGND','VPWR']:g.rect('metal4',left-.4,y-width/2,right+.4,y+width/2)
        else:g.wire('metal4',left,y,right,y,width)
        ports[pin]=dict(layer='metal4',x_um=left,y_um=y,width_um=width)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    for tag,x in zip(['left','right'],xs):
        lines += [f'use {CHILD} {tag}','timestamp 0',f'transform 1 0 {round(x/layout.GRID)} 0 1 {round(dy/layout.GRID)}',
                  'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines.append('<< labels >>')
    for n,(pin,p) in enumerate(ports.items(),1):
        x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal4 {x} {y} {x} {y} 0 {pin}',f'port {n} nsew']
    lines.append('<< end >>');(folder/(NAME+'.mag')).write_text('\n'.join(lines)+'\n')
    (folder/(NAME+'.sch.spice')).write_text(schematic((child/(CHILD+'.sch.spice')).read_text()))
    result=layout.qualify(folder,NAME);raw=folder/(NAME+'.raw.lef');raw.write_bytes((folder/(NAME+'.lef')).read_bytes())
    types=dict(A=('INPUT','SIGNAL'),X=('OUTPUT','SIGNAL'),VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=abstract.restrict(raw.read_text(),ports,types);(folder/(NAME+'.lef')).write_text(text)
    return dict(result,macro=NAME,child=CHILD,child_instances=2,ports=ports,integration_pins=pins,
        placement=dict(x_um=xs,y_um=dy,child_bbox_um=box),gds_sha256=sha(folder/(NAME+'.gds')),lef_sha256=sha(folder/(NAME+'.lef')),
        qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out);_,row,child=parent_row(ROOT/m['identity']['parent'])
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native clock-buffer pair layout')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        folder=out/NAME;folder.mkdir();row=draw(folder,child,row,m['identity']['configuration'])
        (folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n');bound(out)
        result=dict(rows=[row],passed=row['passed'],qualified_phy=False,electrical_qualification_passed=False,
            scope='Two unchanged native BUF8/private-shunt cells with shared M4 rails, geometry/LVS only; fresh RC, phase timing and full clock/PHY qualification remain required')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=result['passed'],qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out,default_plan());print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
