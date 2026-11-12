#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generate connected analog macros from the SAME transistor-level schematics.

Pinned Magic PCells provide devices, contacts, and body guards. Deterministic
M1 fanout / M2 drops / M3 buses provide actual interconnect. MIM top terminals
escape on M4 before descending outside the capacitor (never short its plates).
DRC and LVS are mandatory; generation alone is not a qualification result.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from lvs_utils import schematic_parameters,clean_match,strict_setup

ROOT=Path(__file__).resolve().parents[1]
GRID=.005
# Released I/O macros: multi-row floorplan with M4 trunks and real pin shapes.
ROW_TOPS=['openlvds_io_tx','openlvds_io_rx']
SUPPLIES=['VDDIO','VDDD','VSS']
PIN_KIND=dict(VDDIO='power bidirectional',VDDD='power bidirectional',VSS='ground bidirectional',
    D='signal input',Q='signal output')
# Internal nets whose wiring load limits speed: nearest bus tracks, shortest drops.
FAST_SUFFIXES=['__GPL','__GPR','__GNL','__GNR','__DP','__DN','__XLS__L','__XLS__R','__XLS__AD','__XLS__AB','__XLS__INB',
    '__PP','__PN','__CO','__CL','__NL','__NR','__PL','__PR']
ASPECT_LIMIT=2.
RPM_MIN_WIDTH=1.27

def circuits(text):
    definitions={};current=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('*'): continue
        words=line.split()
        if words[0].lower()=='.subckt':
            current=words[1];definitions[current]=(words[2:],[])
        elif words[0].lower()=='.ends': current=None
        elif current:
            if words[0][0].upper()!='X':
                raise ValueError(f'Implementation contains a non-PDK element: {line}')
            first=next((i for i,w in enumerate(words) if '=' in w),len(words))
            model=words[first-1];nodes=words[1:first-1]
            params=dict(w.split('=',1) for w in words[first:])
            definitions[current][1].append((words[0],nodes,model,params))
    for parent,(_,instances) in definitions.items():
        for instance,nodes,model,_ in instances:
            expected=len(definitions[model][0]) if model in definitions else (
                4 if 'fet_' in model else 3 if 'res_' in model else 2 if 'cap_mim' in model else None)
            if expected is not None and len(nodes)!=expected:
                raise ValueError(f'{parent}/{instance}: {model} expects {expected} terminals, got {len(nodes)}')
    return definitions

def flatten(defs,top):
    ports=defs[top][0];leaves=[]
    def recurse(model,mapping,prefix):
        for instance,nodes,child,params in defs[model][1]:
            translated=[mapping.get(n,prefix+'__'+n) for n in nodes]
            if child in defs:
                recurse(child,dict(zip(defs[child][0],translated)),prefix+'__'+instance)
            elif child.startswith('sky130_fd_pr__'):
                leaves.append(dict(name=prefix+'__'+instance,nodes=translated,model=child,params=params))
            else: raise ValueError(f'{child}: harden digital standard-cell blocks separately')
    recurse(top,dict(zip(ports,ports)),top)
    # Limit physical gate width to bound poly resistance at 800 Mb/s. Parallel
    # fingers retain the schematic's total W/L, with exact 5 nm grid geometry.
    fingers=[]
    for d in leaves:
        if 'nfet' not in d['model'] and 'pfet' not in d['model']:
            fingers.append(d);continue
        w=float(d['params']['w']);n=math.ceil(w/8.)
        while abs(w/n/GRID-round(w/n/GRID))>1e-6:n+=1
        for i in range(n):
            finger=dict(d,name=d['name']+f'_F{i}',params=dict(d['params'],w=f'{w/n:g}'))
            fingers.append(finger)
    return ports,fingers

def primitive_key(device):
    return device['model'],float(device['params']['w']),float(device['params']['l'])

def schematic_text(top,ports,devices):
    lines=['* SPDX-License-Identifier: GPL-3.0-only',f'.subckt {top} '+' '.join(ports)]
    for d in devices:
        lines.append('X'+d['name']+' '+' '.join(d['nodes'])+' '+d['model']+' '+
                     ' '.join(f'{k}={v}' for k,v in schematic_parameters(d).items()))
    return '\n'.join(lines+[f'.ends {top}',''])

def invoke_magic(out,body,logname):
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic/sky130A.magicrc'
    tcl=out/(logname+'.tcl')
    tcl.write_text('drc off\ncrashbackups disable\nlocking disable\n'+body+'\nquit -noprompt\n')
    with (out/(logname+'.log')).open('w') as log:
        result=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(tech),str(tcl)],
                              cwd=out,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(f'Magic failed: {out}/{logname}.log')

def pcell_info(path):
    text=path.read_text();ports={};bounds=[];layer=None;body=[]
    for line in text.splitlines():
        if line.startswith('<< '):layer=line.split()[1]
        if line.startswith('rect ') and layer in ['xpolycontact','ppolyres']:body.append(list(map(int,line.split()[1:])))
        if line.startswith('rect '): bounds.append(list(map(int,line.split()[1:])))
        if line.startswith('rlabel '):
            w=line.split();ports[w[-1]]=(w[1],(int(w[2])+int(w[4]))/2*GRID,
                                        (int(w[3])+int(w[5]))/2*GRID)
    if not bounds: raise ValueError(f'Empty PCell {path}')
    bbox=[min(x[0] for x in bounds)*GRID,min(x[1] for x in bounds)*GRID,
          max(x[2] for x in bounds)*GRID,max(x[3] for x in bounds)*GRID]
    info=dict(ports=ports,bbox=bbox)
    # High-resistance poly body and contacts: the area the RPM implant must cover.
    if body:info['resistor']=[min(x[0] for x in body)*GRID,min(x[1] for x in body)*GRID,
                              max(x[2] for x in body)*GRID,max(x[3] for x in body)*GRID]
    return info

class Geometry:
    def __init__(self): self.layers=defaultdict(list)
    def rect(self,layer,x0,y0,x1,y1):
        coords=[round(min(x0,x1)/GRID),round(min(y0,y1)/GRID),
                round(max(x0,x1)/GRID),round(max(y0,y1)/GRID)]
        if coords[2]<=coords[0] or coords[3]<=coords[1]: raise ValueError('Zero-area geometry')
        self.layers[layer].append(coords)
    def pad(self,layer,x,y,size): self.rect(layer,x-size/2,y-size/2,x+size/2,y+size/2)
    def wire(self,layer,x0,y0,x1,y1,width=.4):
        if x0!=x1 and y0!=y1: raise ValueError('Non-Manhattan wire')
        self.rect(layer,min(x0,x1)-width/2,min(y0,y1)-width/2,
                  max(x0,x1)+width/2,max(y0,y1)+width/2)
    def via12(self,x,y):
        self.pad('metal1',x,y,.4);self.pad('via1',x,y,.26);self.pad('metal2',x,y,.4)
    def via23(self,x,y):
        self.pad('metal2',x,y,.4);self.pad('via2',x,y,.28);self.pad('metal3',x,y,.4)
    def via34(self,x,y):
        self.pad('metal3',x,y,.6);self.pad('via3',x,y,.4);self.pad('metal4',x,y,.6)

def connect_device(geometry,drops,d,cell,info,cx,cy=0.):
    """M1 fanout from each PCell terminal to its own M2 drop track."""
    bb=info['bbox'];pw=info['ports'];model=d['model']
    if 'nfet' in model or 'pfet' in model:
        access=[('D',d['nodes'][0],-1.8),('G',d['nodes'][1],0.),
                ('S',d['nodes'][2],1.8),('B',d['nodes'][3],-2.8)]
    elif 'res_' in model:
        access=[('R1',d['nodes'][0],-1.8),('R2',d['nodes'][1],1.8),('B',d['nodes'][2],-2.8)]
    elif 'cap_mim' in model:
        access=[('C1',d['nodes'][0],bb[0]-2.),('C2',d['nodes'][1],bb[2]+2.)]
    else: raise ValueError(model)
    for pin,net,dx in access:
        if pin not in pw: raise ValueError(f'{cell} missing {pin}: {pw}')
        layer,px,py=pw[pin];py+=cy
        # Long-channel devices have contacts farther from the origin.
        # Keep the added via landing outside the PCell contact metal.
        if pin in ['D','S']:
            dx=(-1 if pin=='D' else 1)*max(abs(dx),abs(px)+.8)
        if pin=='B' and ('nfet' in model or 'pfet' in model):
            dx=-max(abs(dx),abs(pw['D'][1])+2.)
        px+=cx;track=cx+dx
        if 'cap_mim' in model:
            if pin=='C1':
                geometry.wire('metal4',px,py,track,py,.6)
                geometry.via34(track,py)
            else: geometry.wire('metal3',px,py,track,py,.6)
            geometry.via23(track,py)
        else:
            if pin=='B':
                geometry.pad('locali',px,py,.33)
                geometry.pad('viali',px,py,.17)
                geometry.pad('metal1',px,py,.4)
            if pin=='G':
                geometry.wire('metal1',px,py,px,py+.3,.18)
                py+=.3
            geometry.wire('metal1',px,py,track,py,.18)
            geometry.via12(track,py)
        drops[net].append((track,py))

def draw_macro(out,top,ports,devices,library):
    if top in ROW_TOPS:return draw_rows(out,top,ports,devices,library)
    geometry=Geometry();uses=[];drops=defaultdict(list);cursor=10.;ymax=0.
    left_gap,right_gap=(2.5,2.5) if top in ['openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core'] else (5.,6.)
    for i,d in enumerate(devices):
        cell,info=library[primitive_key(d)];bb=info['bbox'];pw=info['ports']
        cx=cursor-bb[0]+left_gap;cursor=cx+bb[2]+right_gap;ymax=max(ymax,bb[3])
        uses.append((cell,f'I{i}',round(cx/GRID),0,[round(v/GRID) for v in bb]))
        connect_device(geometry,drops,d,cell,info,cx)
    # Keep buses above the tallest device including resistor guards and wells.
    origin=math.ceil(ymax+6.)
    internal=set(drops)-set(ports)
    fast_suffixes=['__DP','__DN','__XLS__L','__XLS__R','__XLS__AD','__XLS__AB','__XLS__INB','__XLS__L1','__XLS__R1']
    def priority(net):
        return next((i for i,s in enumerate(fast_suffixes) if net.endswith(s)),len(fast_suffixes)),net
    compact_internal=top in ['openlvds_driver_core','openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core']
    local_ports=top in ['openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core']
    net_order=list(ports)+sorted(internal,key=priority if compact_internal else None)
    labels=[];public={};y=origin
    # An unrelated PCell from another selected macro must not move this bus.
    below=min(library[primitive_key(d)][1]['bbox'][1] for d in devices)-6.
    ceiling=origin+sum((5. if n in ['VDDIO','VDDD','VSS'] else 3. if n in ['OUTP','OUTN'] else .4)+1.4 for n in ports)+6.
    for i,net in enumerate(net_order):
        if net not in drops: raise ValueError(f'Unconnected public port: {net}')
        points=drops[net];xs=[x for x,_ in points]
        width=5. if net in ['VDDIO','VDDD','VSS'] else 3. if net in ['OUTP','OUTN'] else .4
        if compact_internal and net not in ports:
            if priority(net)[0]<len(fast_suffixes):width=.8
            below-=width/2+.7;bus_y=below;below-=width/2+.7
        else:
            y+=width/2+.7;bus_y=y;y+=width/2+.7
        escape=local_ports and net in ports and net not in ['VDDIO','VDDD','VSS']
        left=width/2 if net in ports and not escape else min(xs)-1.
        geometry.wire('metal3',left,bus_y,max(xs)+1.,bus_y,width)
        for x,py in points:
            geometry.wire('metal2',x,py,x,bus_y)
            geometry.via23(x,bus_y)
        labelx=left if net in ports else min(xs)-.5
        label_y=bus_y;label_layer='metal3'
        if escape:
            geometry.via34(labelx,bus_y)
            geometry.wire('metal4',labelx,bus_y,labelx,ceiling,.6)
            label_y=ceiling;label_layer='metal4'
        labels.append((net,labelx,label_y,ports.index(net)+1 if net in ports else None,label_layer))
        if net in ports:public[net]=dict(layer=label_layer,x_um=labelx,y_um=label_y,width_um=.6 if escape else width)
    layout_height=max(y,ceiling if local_ports else y)-min(0,below)+4 if compact_internal else y+ymax+4
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():
        lines.append(f'<< {layer} >>')
        lines.extend('rect '+' '.join(map(str,r)) for r in rects)
    for cell,instance,x,y,bb in uses:
        lines.extend([f'use {cell} {instance}','timestamp 0',f'transform 1 0 {x} 0 1 {y}',
                      'box '+' '.join(map(str,bb))])
    lines.append('<< labels >>')
    for net,lx,ly,port,label_layer in labels:
        lx=round(lx/GRID);ly=round(ly/GRID)
        lines.append(f'rlabel {label_layer} {lx} {ly} {lx} {ly} 0 {net}')
        if port: lines.append(f'port {port} nsew')
    lines.append('<< end >>')
    (out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    # Flattened schematic used for independent connectivity comparison.
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,devices))
    return dict(width_um=cursor+4,height_um=layout_height,
                devices=len(devices),nets=len(net_order),ports=public)

def bus_width(net,ports):
    if net in SUPPLIES:return 5.
    if net in ['OUTP','OUTN']:return 3.
    return .4

def trunk_width(net):return 5. if net in SUPPLIES else 3. if net in ['OUTP','OUTN'] else .6

def fast_rank(net):return next((i for i,x in enumerate(FAST_SUFFIXES) if net.endswith(x)),len(FAST_SUFFIXES))

def split_rows(devices,library,count,ports=()):
    """Schematic order keeps related devices adjacent; tall MIM plates share the last rows.

    Each row break is moved, within a window around the equal-width position,
    to where it cuts the fewest nets (a speed-critical net counts ten times).
    A net cut by a break needs a trunk and a long bus in two rows, so cutting
    one side of a symmetric group would load it more than its twin.
    """
    order=[d for d in devices if 'cap_mim' not in d['model']]+[d for d in devices if 'cap_mim' in d['model']]
    def span(d):
        bb=library[primitive_key(d)][1]['bbox'];return bb[2]-bb[0]+2*(3.5 if 'cap_mim' in d['model'] else 2.5)
    spans=list(map(span,order));target=sum(spans)/count;window=12
    first={};last={}
    for i,d in enumerate(order):
        for net in d['nodes']:
            if net in ports:continue
            first.setdefault(net,i);last[net]=i
    def cost(cut):  # break between order[cut-1] and order[cut]
        return sum(10 if fast_rank(net)<len(FAST_SUFFIXES) else 1 for net in first if first[net]<cut<=last[net])
    cuts=[];position=0.;index=0
    for row in range(1,count):
        goal=row*target
        while index<len(order) and position+spans[index]/2<=goal:position+=spans[index];index+=1
        low=max(cuts[-1]+1 if cuts else 1,index-window);high=min(len(order)-1,index+window)
        if low>high:break
        cuts.append(min(range(low,high+1),key=lambda c:(cost(c),abs(c-index))))
    bounds=[0,*cuts,len(order)]
    return [order[a:b] for a,b in zip(bounds,bounds[1:]) if b>a]

def rows_geometry(ports,devices,library,count):
    rows=split_rows(devices,library,count,ports)
    present=[{n for d in row for n in d['nodes']} for row in rows]
    every=set().union(*present);internal=every-set(ports)
    missing=[n for n in ports if n not in every]
    if missing:raise ValueError(f'Unconnected public port: {missing[0]}')
    net_order=list(ports)+sorted(internal)
    # Bus tracks, nearest the devices first: fast internal nets, other internal
    # nets, signal pins, outputs, then the wide supplies. A signal drop then
    # never crosses the supply buses.
    bus_order=(sorted(internal,key=lambda net:(fast_rank(net),net))+[n for n in ports if n not in SUPPLIES+['OUTP','OUTN']]
               +[n for n in ports if n in ['OUTP','OUTN']]+[n for n in ports if n in SUPPLIES])
    # A net needs a vertical trunk if it is a pin or spans more than one row.
    trunks={};cursor=2.
    for net in net_order:
        if net in ports or sum(net in p for p in present)>1:
            w=trunk_width(net);trunks[net]=cursor+w/2;cursor+=w+1.4
    x0=cursor+6.;geometry=Geometry();uses=[];labels=[];span={};width=0.;y=4.;index=0;hints=[]
    for row,nets in zip(rows,present):
        infos=[library[primitive_key(d)] for d in row]
        cy=y+6.-min(info['bbox'][1] for _,info in infos);top=cy+max(info['bbox'][3] for _,info in infos)
        drops=defaultdict(list);cursor=x0
        for d,(cell,info) in zip(row,infos):
            bb=info['bbox'];gap=3.5 if 'cap_mim' in d['model'] else 2.5
            cx=cursor-bb[0]+gap;cursor=cx+bb[2]+gap
            uses.append((cell,f'I{index}',round(cx/GRID),round(cy/GRID),[round(v/GRID) for v in bb]));index+=1
            connect_device(geometry,drops,d,cell,info,cx,cy)
            if 'resistor' in info:
                # Magic derives RPM as poly plus 0.2 um, only 0.75 um wide for
                # this 0.35 um resistor. rpm.1a requires 1.27 um, so widen it.
                rx0,ry0,rx1,ry1=info['resistor'];half=max(RPM_MIN_WIDTH,rx1-rx0+.4)/2;middle=cx+(rx0+rx1)/2
                hints.append((middle-half,cy+ry0-.2,middle+half,cy+ry1+.2))
        width=max(width,cursor+4.);y=math.ceil(top+6.)
        for net in bus_order:
            if net not in drops:continue
            w=bus_width(net,ports);points=drops[net];xs=[x for x,_ in points]
            y+=w/2+.7;bus_y=y;y+=w/2+.7
            left=trunks.get(net,min(xs)-1.)
            geometry.wire('metal3',left,bus_y,max(xs)+1.,bus_y,w)
            for x,py in points:
                geometry.wire('metal2',x,py,x,bus_y)
                geometry.via23(x,bus_y)
            if net in trunks:
                # Wide current-carrying crossings get a full via array.
                n=int((min(w,trunk_width(net))/2-.3)/.8)
                for i in range(-n,n+1):
                    for j in range(-n,n+1):geometry.via34(trunks[net]+i*.8,bus_y+j*.8)
                low,high=span.get(net,(bus_y,bus_y));reach=max(w/2,.3)
                span[net]=(min(low,bus_y-reach),max(high,bus_y+reach))
            else:labels.append((net,min(xs)-.5,bus_y,min(xs)-.5,bus_y,None,'metal3'))
        y+=2.
    height=y+4.;public={}
    for net,x in trunks.items():
        w=trunk_width(net);low,high=span[net]
        if net in ports:low=0.
        if net in SUPPLIES:high=height
        geometry.rect('metal4',x-w/2,low,x+w/2,high)
        if net in ports:
            # Supplies are full-height straps; signals are 2 um stubs on the bottom edge.
            top=high if net in SUPPLIES else 2.
            labels.append((net,x-w/2,0.,x+w/2,top,ports.index(net)+1,'metal4'))
            public[net]=dict(layer='metal4',x_um=x,y_um=1.,width_um=w,length_um=top)
        else:labels.append((net,x,low+.3,x,low+.3,None,'metal4'))
    return geometry,uses,labels,public,width,height,len(net_order),len(rows),hints

def draw_rows(out,top,ports,devices,library):
    """Multi-row floorplan closest to square; single-row output is a 4 mm strip."""
    best=None
    for count in range(1,min(len(devices),48)+1):
        candidate=rows_geometry(ports,devices,library,count)
        aspect=max(candidate[4]/candidate[5],candidate[5]/candidate[4])
        if best is None or aspect<best[0]:best=(aspect,candidate)
    aspect,(geometry,uses,labels,public,width,height,nets,count,hints)=best
    if aspect>ASPECT_LIMIT:raise ValueError(f'{top}: no floorplan within aspect limit')
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():
        lines.append(f'<< {layer} >>')
        lines.extend('rect '+' '.join(map(str,r)) for r in rects)
    for cell,instance,x,y,bb in uses:
        lines.extend([f'use {cell} {instance}','timestamp 0',f'transform 1 0 {x} 0 1 {y}',
                      'box '+' '.join(map(str,bb))])
    lines.append('<< labels >>')
    for net,ax,ay,bx,by,port,layer in labels:
        lines.append(f'rlabel {layer} '+' '.join(str(round(v/GRID)) for v in [ax,ay,bx,by])+f' 0 {net}')
        if port:lines.append(f'port {port} nsew '+PIN_KIND.get(net,'analog bidirectional'))
    # The fixed bounding box becomes the LEF SIZE and the GDS place-and-route
    # boundary that digital flows require of a hard macro.
    width=math.ceil(width/.01-1e-6)*.01;height=math.ceil(height/.01-1e-6)*.01
    lines += ['<< properties >>',f'string FIXED_BBOX 0 0 {round(width/GRID)} {round(height/GRID)}']
    if hints:
        # Snap outward to even file units so the halved internal value is exact.
        snapped=[f(v/GRID/2-1e-6 if f is math.floor else v/GRID/2+1e-6)*2 if abs(v/GRID/2-round(v/GRID/2))>1e-6 else round(v/GRID/2)*2
                 for box in hints for v,f in zip(box,[math.floor,math.floor,math.ceil,math.ceil])]
        lines.append('string MASKHINTS_RPM '+' '.join(map(str,snapped)))
    lines.append('<< end >>')
    (out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,devices))
    return dict(width_um=width,height_um=height,aspect_ratio=aspect,rows=count,
                devices=len(devices),nets=nets,ports=public)

# Flattening drops mask hints, so Magic's own rpm.1 check would not see the
# widened implant that the GDS carries. The pinned Magic reads the property in
# file units but stores what it is given in internal units (half as large with
# magscale 1 2); accept only a value that reads back identical to the source.
KEEP_RPM_HINTS='''if {$rpm_hints ne ""} {
    property MASKHINTS_RPM {*}$rpm_hints
    if {[property MASKHINTS_RPM] ne $rpm_hints} {
        set scaled {}
        foreach value $rpm_hints {lappend scaled [expr {$value/2}]}
        property MASKHINTS_RPM {*}$scaled
    }
    if {[property MASKHINTS_RPM] ne $rpm_hints} {error "RPM mask hints were not preserved on the flattened cell"}
}'''

def qualify(out,top):
    # Extract ordinary device netlist for LVS before parasitic extraction.
    body=f'''load {top}
select top cell
{'gds datestamp 0' if top in ROW_TOPS else ''}
gds write {top}.gds
lef write {top}.lef{' -hide' if top in ROW_TOPS else ''}
{'set rpm_hints [property MASKHINTS_RPM]' if top in ROW_TOPS else ''}
flatten {top}_flat
load {top}_flat
{KEEP_RPM_HINTS if top in ROW_TOPS else ''}
select clear
select top cell
box values -100um -100um 10000um 10000um
{'drc style drc(full)' if top in ROW_TOPS else ''}
drc euclidean on
drc on
drc check
drc catchup
set errors [drc listall why]
set f [open {top}.drc.txt w]
puts $f $errors
close $f
set f [open {top}.drc_count.txt w]
puts $f [drc listall count total]
close $f
extract all
ext2spice lvs
ext2spice -o {top}.lvs.spice {top}_flat.ext
'''
    if top in ROW_TOPS:body+='antennacheck debug\nantennacheck\n'
    invoke_magic(out,body,'extract_'+top)
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    tech=strict_setup(out/(top+'.lvs_setup.tcl'),tech)
    report=out/(top+'.lvs.log')
    command=['netgen','-batch','lvs',f'{out}/{top}.lvs.spice {top}_flat',
             f'{out}/{top}.sch.spice {top}',str(tech),str(report)]
    result=subprocess.run(command,cwd=out,capture_output=True,text=True)
    (out/(top+'.netgen.log')).write_text(result.stdout+result.stderr)
    text=report.read_text() if report.exists() else ''
    drc=(out/(top+'.drc_count.txt')).read_text().strip()
    lvs=clean_match(text,result.returncode)
    extra={}
    if top in ROW_TOPS:
        # Magic lists the wells as a LEF obstruction. Wells are not a routing
        # layer, and an abstract built from that LEF would show an untapped
        # well to a top-level DRC. Integrators keep cells out with a halo.
        lef=out/(top+'.lef');kept=[];skip=False
        for line in lef.read_text().splitlines():
            words=line.split()
            if words[:1]==['LAYER']:skip=words[1]=='nwell'
            elif words[:1]==['END']:skip=False
            if not skip:kept.append(line)
        lef.write_text('\n'.join(kept)+'\n')
        log=(out/('extract_'+top+'.log')).read_text()
        extra=dict(antenna_count=len(re.findall(r'(?i)antenna violation',log)),
            lef_sha256=hashlib.sha256((out/(top+'.lef')).read_bytes()).hexdigest())
        lvs=lvs and extra['antenna_count']==0
    return dict(**extra,drc_count=drc,lvs_passed=lvs,
                lvs_source_sha256=hashlib.sha256((out/(top+'.sch.spice')).read_bytes()).hexdigest(),
                lvs_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None,
                passed=drc=='0' and lvs,gds=str((out/(top+'.gds')).relative_to(ROOT)))

def erc(ports,devices):
    """Static electrical rules on the LVS-checked netlist; returns violations."""
    errors=[];terminals=defaultdict(list)
    for d in devices:
        kinds=['D','G','S','B'] if 'fet_' in d['model'] else ['R1','R2','B'] if 'res_' in d['model'] else ['C1','C2']
        for kind,net in zip(kinds,d['nodes']):terminals[net].append((d['name'],kind))
        if 'fet_' in d['model']:
            drain,gate,source,body=d['nodes'];thin='01v8' in d['model']
            if 'nfet' in d['model'] and body!='VSS':errors.append(f'{d["name"]}: NMOS body {body} is not VSS')
            if 'pfet' in d['model'] and body not in (['VDDD'] if thin else ['VDDIO']):
                errors.append(f'{d["name"]}: PMOS well {body} is not its domain supply')
            if thin and 'VDDIO' in d['nodes']:errors.append(f'{d["name"]}: 1.8 V device on VDDIO')
        elif 'res_' in d['model'] and d['nodes'][2]!='VSS':errors.append(f'{d["name"]}: resistor body {d["nodes"][2]} is not VSS')
    for net,uses in sorted(terminals.items()):
        if net in ports:continue
        # A gate needs a conductive path to something that can set its level.
        if all(kind=='G' for _,kind in uses):errors.append(f'{net}: floating gate net')
        if len(uses)<2:errors.append(f'{net}: single-terminal net')
    for net in ports:
        if net not in terminals:errors.append(f'{net}: unconnected pin')
    return errors

DENSITY_SCRIPT='''import json,pya
layout=pya.Layout();layout.read(input_gds);cell=layout.cell(top_cell);box=cell.dbbox();result={}
for name,layer in [('li1',67),('met1',68),('met2',69),('met3',70),('met4',71),('met5',72)]:
    region=pya.Region(cell.begin_shapes_rec(layout.layer(layer,20)));region.merge()
    result[name]=region.area()*layout.dbu**2/(box.width()*box.height())
json.dump(dict(width_um=box.width(),height_um=box.height(),density=result),open(output_json,'w'),indent=2)
'''

def signoff(top,info,defs):
    """Checks beyond Magic DRC and Netgen LVS for one released macro."""
    import xml.etree.ElementTree as ET
    gds=ROOT/info['gds'];work=gds.parent/('signoff_'+top);work.mkdir(exist_ok=True)
    deck=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout/drc/sky130A_mr.drc'
    report=work/'klayout_drc.lyrdb';report.unlink(missing_ok=True)
    command=['klayout','-b','-zz','-r',str(deck),'-rd',f'input={gds}','-rd',f'top_cell={top}','-rd',f'report={report}',
        '-rd','feol=true','-rd','beol=true','-rd','offgrid=true','-rd','floating_metal=false','-rd','seal=false','-rd','threads=4']
    result=subprocess.run(command,cwd=work,capture_output=True,text=True)
    (work/'klayout_drc.log').write_text(result.stdout+result.stderr)
    categories={}
    if result.returncode==0 and report.exists():
        for item in ET.parse(report).getroot().iter('item'):
            name=item.findtext('category','').strip("'");categories[name]=categories.get(name,0)+1
        klayout=sum(categories.values())
    else:klayout=None
    (work/'density.py').write_text(DENSITY_SCRIPT)
    density_path=work/'density.json';density_path.unlink(missing_ok=True)
    result=subprocess.run(['klayout','-b','-zz','-r',str(work/'density.py'),'-rd',f'input_gds={gds}','-rd',f'top_cell={top}',
        '-rd',f'output_json={density_path}'],cwd=work,capture_output=True,text=True)
    (work/'density.log').write_text(result.stdout+result.stderr)
    density=json.loads(density_path.read_text()) if density_path.exists() else None
    violations=erc(*flatten(defs,top))
    checks=dict(magic_drc=info.get('drc_count')=='0',netgen_lvs=bool(info.get('lvs_passed')),antenna=info.get('antenna_count')==0,
        klayout_drc=klayout==0,erc=not violations,density_reported=density is not None,
        aspect=bool(density and max(density['width_um']/density['height_um'],density['height_um']/density['width_um'])<=ASPECT_LIMIT))
    return dict(passed=all(checks.values()),checks=checks,klayout_drc_count=klayout,klayout_drc_categories=categories,
        erc_violations=violations,density=density,gds_sha256=hashlib.sha256(gds.read_bytes()).hexdigest(),
        fill_policy='Macro ships unfilled; chip-level fill must keep out of the macro boundary on li1-met4 and meet minimum density over the whole die',
        xor='Not applicable: the GDS has a single Magic streamout, cross-checked by KLayout DRC and Netgen LVS')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--signoff',action='store_true',help='Antenna, KLayout DRC, density and ERC on the released I/O macros in current.json')
    p.add_argument('--design',default='openlvds_driver_core,openlvds_receiver_core,openlvds_delay_line,openlvds_dll_analog,lvds_bias,openlvds_io_tx,openlvds_io_rx')
    p.add_argument('--keep-existing',action='store_true',help='Retain other qualified macros from the identical schematic revision')
    a=p.parse_args()
    source=(ROOT/'analog/openlvds.spice').read_bytes()
    if a.signoff:
        current=json.loads((ROOT/'build/layout/current.json').read_text())
        if current['source_sha256']!=hashlib.sha256(source).hexdigest():raise SystemExit('Layout belongs to another schematic')
        defs=circuits(source.decode());results={}
        for top in ROW_TOPS:
            if top not in current['designs']:raise SystemExit(top+': no layout to sign off')
            results[top]=signoff(top,current['designs'][top],defs)
            print(top,json.dumps({k:v for k,v in results[top].items() if k not in ['klayout_drc_categories','erc_violations']}),flush=True)
        summary=dict(passed=all(v['passed'] for v in results.values()),source_sha256=current['source_sha256'],
            layout_fingerprint=current['fingerprint'],producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),designs=results)
        target=ROOT/'build/io_300/signoff';target.mkdir(parents=True,exist_ok=True)
        (target/'current.json').write_text(json.dumps(summary,indent=2)+'\n')
        return 0 if summary['passed'] else 1
    fingerprint=hashlib.sha256(source+Path(__file__).read_bytes()+
                 (ROOT/'scripts/lvs_utils.py').read_bytes()+
                 (ROOT/'requirements.json').read_bytes()).hexdigest()
    out=ROOT/'build/layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    defs=circuits(source.decode());designs={}
    for top in a.design.split(','):
        designs[top]=flatten(defs,top)
    keys=sorted({primitive_key(d) for _,devs in designs.values() for d in devs})
    body=[];names={}
    for i,(model,w,l) in enumerate(keys):
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12]
        names[(model,w,l)]=cell
        # Remove only these generated cells to avoid accumulating old labels.
        (out/(cell+'.mag')).unlink(missing_ok=True)
        body.extend([f'load {cell} -silent','box values 0 0 0 0',
            f'set p [sky130::{model}_defaults]',f'dict set p w {w}',f'dict set p l {l}',
            *(['dict set p botc 0'] if 'nfet' in model or 'pfet' in model else []),
            f'sky130::{model}_draw $p',f'save {cell}'])
    invoke_magic(out,'\n'.join(body),'pcells')
    library={key:(name,pcell_info(out/(name+'.mag'))) for key,name in names.items()}
    results={}
    if a.keep_existing:
        previous=json.loads((ROOT/'build/layout/current.json').read_text())
        results={k:v for k,v in previous['designs'].items() if k not in designs}
        if any(not v.get('passed') for v in results.values()):raise ValueError('Cannot retain failed layouts')
        for name,info in results.items():
            pins,devices=flatten(defs,name)
            archived=(ROOT/info['gds']).with_suffix('.sch.spice')
            expected=schematic_text(name,pins,devices).encode()
            if not archived.exists() or archived.read_bytes()!=expected:
                raise ValueError(name+': schematic changed; regenerate this macro')
            info['retained_from_source_sha256']=previous['source_sha256']
    for top,(ports,devs) in designs.items():
        info=draw_macro(out,top,ports,devs,library)
        try: info.update(qualify(out,top))
        except (OSError,RuntimeError) as error: info.update(passed=False,error=str(error))
        results[top]=info
        print(top,json.dumps({k:v for k,v in info.items() if k!='ports'}),flush=True)
    summary=dict(source_sha256=hashlib.sha256(source).hexdigest(),fingerprint=fingerprint,
                 passed=all(v.get('passed',False) for v in results.values()),designs=results,
                 output=str(out.relative_to(ROOT)))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (ROOT/'build/layout/current.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
