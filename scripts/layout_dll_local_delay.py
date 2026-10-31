#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build isolated DLL GDS with local delay and quiet-comparator islands."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from layout import (ROOT,GRID,Geometry,circuits,flatten,primitive_key,pcell_info,
                    invoke_magic,draw_macro,schematic_text,qualify)


def partition(devices,ports):
    averages={'XRU','XRD','XCU','XCD'}
    quiet=[];core=[]
    for d in devices:
        name=d['name'];monitor='__XAREA__' in name
        leaf=name.rsplit('__',1)[-1]
        average=leaf in averages or re.fullmatch(r'XC[UD]_\d+',leaf)
        if monitor and not average:quiet.append(d)
        else:core.append(d)
    cn={n for d in core for n in d['nodes']};qn={n for d in quiet for n in d['nodes']}
    shared=sorted(cn&qn)
    cp=[p for p in ports if p in cn]+[n for n in shared if n not in ports]
    qp=[p for p in ports if p in qn]+[n for n in shared if n not in ports]
    if not core or not quiet or set(ports)-(cn|qn):raise ValueError('Invalid control/monitor partition')
    if any(n in shared for n in ['CLK','PD_ENABLE','PH0','PH90','PH180','PH270','FB','PD_REF','UP','DN']):
        raise ValueError('Fast clocks/pump signals must remain within the control island')
    return core,quiet,cp,qp,shared


def bounds(path):
    boxes=[];tx=ty=0
    for line in path.read_text().splitlines():
        w=line.split()
        if not w:continue
        if w[0]=='rect':boxes.append(list(map(int,w[1:5])))
        elif w[0]=='transform':tx,ty=int(w[3]),int(w[6])
        elif w[0]=='box':
            x0,y0,x1,y1=map(int,w[1:5]);boxes.append([x0+tx,y0+ty,x1+tx,y1+ty])
    if not boxes:raise ValueError('Empty island')
    return [min(b[0] for b in boxes)*GRID,min(b[1] for b in boxes)*GRID,
            max(b[2] for b in boxes)*GRID,max(b[3] for b in boxes)*GRID]


def write_parent(out,top,ports,core_info,quiet_info,shared):
    geometry=Geometry();cbox=bounds(out/'dll_control_island.mag');qbox=bounds(out/'dll_monitor_island.mag')
    cxy=(10-cbox[0],10-cbox[1]);qxy=(cbox[2]-cbox[0]+110-qbox[0],10-qbox[1])
    coords={}
    for tag,info,(ox,oy) in [('core',core_info,cxy),('quiet',quiet_info,qxy)]:
        coords[tag]={n:dict(p,x_um=p['x_um']+ox,y_um=p['y_um']+oy) for n,p in info['ports'].items()}
    y=max(cbox[3]+cxy[1],qbox[3]+qxy[1])+20
    labels=[];public={}
    for i,net in enumerate(shared):
        width=5 if net in ['VDDD','VSS','VDDIO'] else .4
        y+=width/2+1.4;ends=[]
        for tag,(ox,oy),bb in [('core',cxy,cbox),('quiet',qxy,qbox)]:
            pin=coords[tag][net];x,py=pin['x_um'],pin['y_um']
            if pin['layer']=='metal3':
                # Supply pins share x within a child. Escape to distinct tracks
                # outside the child before turning upward, avoiding rail shorts.
                escape=ox+bb[0]-10-4*i
                geometry.wire('metal3',escape,py,x,py,width)
                geometry.via34(escape,py);x=escape
            geometry.wire('metal4',x,py,x,y,.6);geometry.via34(x,y);ends.append(x)
        geometry.wire('metal3',min(ends),y,max(ends),y,width)
        labels.append((net,min(ends),y,None,'metal3'))
        y+=width/2+1.4
    for i,net in enumerate(ports,1):
        pin=coords['core'].get(net,coords['quiet'].get(net))
        if pin is None:raise ValueError('Unrouted public pin '+net)
        # Promote the local child port directly: no long clock escape through
        # the monitor bank or added common bus height on the fast paths.
        x,py=pin['x_um'],pin['y_um'];layer=pin['layer']
        geometry.pad(layer,x,py,.6 if layer=='metal4' else pin['width_um'])
        labels.append((net,x,py,i,layer));public[net]=dict(pin)
    # Preserve useful root-level observation labels without adding ports.
    for line in (out/'dll_control_island.mag').read_text().splitlines():
        w=line.split()
        if w and w[0]=='rlabel' and w[-1] in {top+'__'+n for n in ['CTRL','VCOPY','DRIVE','NC']}:
            layer=w[1];x=(int(w[2])+int(w[4]))/2*GRID+cxy[0];py=(int(w[3])+int(w[5]))/2*GRID+cxy[1]
            geometry.pad(layer,x,py,.4);labels.append((w[-1],x,py,None,layer))
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():
        lines+=['<< '+layer+' >>']+['rect '+' '.join(map(str,r)) for r in rects]
    for cell,xy,bb in [('dll_control_island',cxy,cbox),('dll_monitor_island',qxy,qbox)]:
        x,py=[round(v/GRID) for v in xy]
        lines += [f'use {cell} {cell}','timestamp 0',f'transform 1 0 {x} 0 1 {py}',
                  'box '+' '.join(str(round(v/GRID)) for v in bb)]
    lines+=['<< labels >>']
    for net,x,py,index,layer in labels:
        x,py=round(x/GRID),round(py/GRID);lines.append(f'rlabel {layer} {x} {py} {x} {py} 0 {net}')
        if index:lines.append(f'port {index} nsew')
    lines+=['<< end >>'];(out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    return dict(ports=public,width_um=qbox[2]+qxy[0]+10,height_um=y+10,
                control_island_bbox_um=cbox,monitor_island_bbox_um=qbox,shared_nets=shared)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--local-comparators',action='store_true',help='Route each quiet comparator in its own local island')
    a=p.parse_args()
    path=a.source.resolve()
    if not path.is_relative_to(ROOT):p.error('Source must reside in OpenLVDS')
    source=path.read_bytes();defs=circuits(source.decode());top='openlvds_dll_analog';ports,devices=flatten(defs,top)
    core,quiet,cp,qp,shared=partition(devices,ports)
    code=[Path(__file__),ROOT/'scripts/layout.py',ROOT/'scripts/lvs_utils.py',
          ROOT/'scripts/layout_dll_candidate.py',ROOT/'scripts/layout_local_delay.py']
    if a.local_comparators:code.append(ROOT/'scripts/layout_local_monitor.py')
    identity=source+b''.join(f.read_bytes() for f in code)+(ROOT/'requirements.json').read_bytes()+str(a.local_comparators).encode()
    fingerprint=hashlib.sha256(identity).hexdigest();out=ROOT/'build/diagnostics/dll_layout'/fingerprint[:16]
    out.mkdir(parents=True,exist_ok=True);(out/'candidate.spice').write_bytes(source)
    keys=sorted({primitive_key(d) for d in devices});body=[];names={}
    for model,w,l in keys:
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];names[(model,w,l)]=cell
        body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                 f'dict set p w {w}',f'dict set p l {l}']
        if 'nfet' in model or 'pfet' in model:body+=['dict set p botc 0']
        body += [f'sky130::{model}_draw $p',f'save {cell}']
    invoke_magic(out,'\n'.join(body),'pcells')
    cells={key:(name,pcell_info(out/(name+'.mag'))) for key,name in names.items()}
    from layout_local_delay import draw as draw_control
    core_info=draw_control(out,top,cp,core,cells)
    (out/(top+'.mag')).replace(out/'dll_control_island.mag')
    if a.local_comparators:
        from layout_local_monitor import draw
        quiet_info=draw(out,'dll_monitor_island',qp,quiet,cells)
    else:quiet_info=draw_macro(out,'dll_monitor_island',qp,quiet,cells)
    # Core was drawn with the local clock routing policy; its name is private.
    info=write_parent(out,top,ports,core_info,quiet_info,shared)
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,devices))
    info.update(qualify(out,top));info.update(devices=len(devices),control_devices=len(core),monitor_devices=len(quiet))
    summary=dict(diagnostic=True,local_delay_sections=True,local_comparators=a.local_comparators,source_sha256=hashlib.sha256(source).hexdigest(),fingerprint=fingerprint,
        passed=info['passed'],designs={top:info},source=str(path.relative_to(ROOT)))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],output=str(out),drc_count=info['drc_count'],lvs_passed=info['lvs_passed'])),flush=True)
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
