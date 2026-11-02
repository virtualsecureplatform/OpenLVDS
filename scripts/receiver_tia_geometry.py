# SPDX-License-Identifier: GPL-3.0-only
"""Keep the first-inverter feedback loop local, with four below-row buses."""
from collections import Counter,defaultdict
import math,re,json
from layout import Geometry,GRID,primitive_key,schematic_text


import receiver_soft_frontend_geometry as classification

LOCAL_BUSES = ['CT','CO','CL','RESTORE0']


def critical(d):
    return classification.critical(d) or bool(re.search(r'__XRFB[0-9]+$',d['name']))


def stage(d):
    name=d['name']
    if re.search(r'__XIB[12]__',name): return 3
    if re.search(r'__XIB0__|__XRFB[0-9]+$',name): return 2
    if re.search(r'__(?:XCT|XC0|XC1|XCD|XCM)(?:_F|$)',name): return 1
    return 0


def ordered(devices):
    feedback=[d for d in devices if re.search(r'__XRFB[0-9]+$',d['name'])]
    if len(feedback) not in [2,4]:raise ValueError('Require the declared series-feedback inverter circuit')
    if any(n.endswith(('__AMP_CT','__AMP_OUT')) for d in devices for n in d['nodes']):
        raise ValueError('Feedback-inverter geometry cannot accept an extra differential amplifier')
    bulk=[d for d in devices if not critical(d)]
    result=bulk+sorted((d for d in devices if critical(d)),key=stage)
    signature=lambda ds:Counter(json.dumps(d,sort_keys=True) for d in ds)
    if signature(result)!=signature(devices):raise ValueError('Compact placement changed the circuit')
    return result


def draw_macro(out,top,ports,devices,library):
    if top!='openlvds_receiver_core':raise ValueError('Receiver-only feedback-inverter layout')
    devices=ordered(devices);bulk=[d for d in devices if not critical(d)];fast=[d for d in devices if critical(d)]
    if not fast:raise ValueError('Missing decision/restoration cluster')
    allnets=sorted({n for d in devices for n in d['nodes']});power={'VDDIO','VDDD','VSS'}
    maxw=max(library[primitive_key(d)][1]['bbox'][2]-library[primitive_key(d)][1]['bbox'][0] for d in devices)
    maxh=max(library[primitive_key(d)][1]['bbox'][3]-library[primitive_key(d)][1]['bbox'][1] for d in devices)
    columns=4;rows=math.ceil(len(bulk)/columns);lane_x={};channel=0.
    for net in allnets:
        width=2. if net in power else .6
        channel+=width/2+.8;lane_x[net]=channel;channel+=width/2
    pitch=maxw+14.+channel;geometry=Geometry();uses=[];drops=defaultdict(list);trunks=defaultdict(list);ymax=0.;cursor=10.
    for i,d in enumerate(devices):
        cell,info=library[primitive_key(d)];bb=info['bbox'];pw=info['ports'];isfast=critical(d)
        if isfast:
            cx=cursor-bb[0]+2.5;cursor=cx+bb[2]+2.5;cy=8.+rows*(maxh+10.)-bb[1];column=None
        else:
            row,column=divmod(i,columns);cx=10.+column*pitch+6.-bb[0];cy=8.+row*(maxh+10.)-bb[1]
        ymax=max(ymax,cy+bb[3]);uses.append((cell,f'I{i}',round(cx/GRID),round(cy/GRID),[round(v/GRID) for v in bb]))
        model=d['model']
        if 'nfet' in model or 'pfet' in model:access=[('D',d['nodes'][0],-1.8),('G',d['nodes'][1],0.),('S',d['nodes'][2],1.8),('B',d['nodes'][3],-2.8)]
        elif 'res_' in model:access=[('R1',d['nodes'][0],-1.8),('R2',d['nodes'][1],1.8),('B',d['nodes'][2],-2.8)]
        else:raise ValueError('Compact receiver has unsupported primitive '+model)
        for lane,(pin,net,dx) in enumerate(access):
            layer,px,py=pw[pin]
            if pin in ['D','S']:dx=(-1 if pin=='D' else 1)*max(abs(dx),abs(px)+.8)
            if pin=='B' and ('nfet' in model or 'pfet' in model):dx=-max(abs(dx),abs(pw['D'][1])+2.)
            px+=cx;py+=cy;track=cx+dx
            if pin=='B':
                geometry.pad('locali',px,py,.33);geometry.pad('viali',px,py,.17);geometry.pad('metal1',px,py,.4)
            if pin=='G':geometry.wire('metal1',px,py,px,py+.3,.18);py+=.3
            geometry.wire('metal1',px,py,track,py,.18);geometry.via12(track,py)
            if isfast:drops[net].append((track,py))
            else:
                # Row-local M2 access ends above its PCell. M3 fans out to
                # a per-net/per-column M4 trunk, shared by all rows of that net.
                launch=8.+row*(maxh+10.)+maxh+2.+lane
                x=10.+column*pitch+maxw+12.+lane_x[net]
                geometry.wire('metal2',track,py,track,launch);geometry.via23(track,launch)
                geometry.wire('metal3',track,launch,x,launch);geometry.via34(x,launch)
                trunks[(net,column)].append((x,launch))
    origin=math.ceil(ymax+6.);y=origin;labels=[];public={}
    suffixes=['__FB1','__FB2','__FB3','__NL','__NR','__PL','__PR','__PP','__PN','__CO','__CL','__CT',
              '__RESTORE0','__RESTORE1','__NT','__PT','__NBC','__PPRT','__PPRB','__PNRT','__PNRB']
    priority=lambda n:(next((i for i,s in enumerate(suffixes) if n.endswith(s)),len(suffixes)),n)
    order=sorted(set(allnets)-set(ports),key=priority)+list(ports)
    for net in order:
        points=list(drops[net])+[ps[0] for (n,c),ps in trunks.items() if n==net]
        if not points:raise ValueError('Unconnected net '+net)
        width=5. if net in power else .4;y+=width/2+.7;bus_y=y;y+=width/2+.7
        leaf=next((leaf for leaf in LOCAL_BUSES if net.endswith('__'+leaf)),None)
        if leaf is not None:
            if net in ports or any(n==net for n,c in trunks):
                raise ValueError('Below-row buses require an internal net confined to critical devices')
            # The folded row's highest M3 launch is five microns below this
            # row. Four 0.4 um buses on 1.2 um pitch fit in the existing gap.
            # Reserve upper channel space while keeping the three decision
            # buses local. Feedback intermediate nodes use the first upper
            # channels and never enter folded bias trunks.
            bus_y=8.+rows*(maxh+10.)-4.+1.2*LOCAL_BUSES.index(leaf)
        xs=[p[0] for p in points];left=width/2 if net in ports else min(xs)-1.
        geometry.wire('metal3',left,bus_y,max(xs)+1.,bus_y,width)
        for x,py in drops[net]:geometry.wire('metal2',x,py,x,bus_y);geometry.via23(x,bus_y)
        for (n,c),ps in trunks.items():
            if n!=net:continue
            x=ps[0][0];geometry.wire('metal4',x,min(p[1] for p in ps),x,bus_y,2. if net in power else .6);geometry.via34(x,bus_y)
        labels.append((net,left if net in ports else min(xs)-.5,bus_y,ports.index(net)+1 if net in ports else None))
        if net in ports:public[net]=dict(layer='metal3',x_um=left,y_um=bus_y,width_um=width)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():lines+=['<< '+layer+' >>']+['rect '+' '.join(map(str,r)) for r in rects]
    for cell,instance,x,cy,bb in uses:lines += [f'use {cell} {instance}','timestamp 0',f'transform 1 0 {x} 0 1 {cy}','box '+' '.join(map(str,bb))]
    lines.append('<< labels >>')
    for net,x,ly,port in labels:
        x=round(x/GRID);ly=round(ly/GRID);lines.append(f'rlabel metal3 {x} {ly} {x} {ly} 0 {net}')
        if port:lines.append(f'port {port} nsew')
    lines.append('<< end >>');(out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,devices))
    return dict(width_um=max(cursor,10.+columns*pitch)+4.,height_um=y+4.,devices=len(devices),nets=len(order),ports=public)
