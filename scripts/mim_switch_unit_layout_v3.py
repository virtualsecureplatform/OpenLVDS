# SPDX-License-Identifier: GPL-3.0-only
"""Compact deterministic routing of the five-device native MIM switch unit."""
from pathlib import Path
import layout
import mim_switch_unit_v2 as unit

VERSION='compact-mim-switch-routing-v2.2'


def plan():
    return dict(mos_centers=[[2.,2.],[6.,2.],[10.,2.]],cap_centers=[[4.5,2.5],[9.,2.5]],
        tracks=dict(B=-1.5,D=-.8,G=0.,S=.8),gate_escape=.3,cap_escape_y=4.5,
        buses=dict(NODE=.3,EN=6.2,ENB=7.,VDD=7.9,VSS=8.9,CAP=5.4),
        bus_left=.3,bus_right=11.8,signal_width=.4,power_width=.6,drop_width=.18)


def draw(out,library,configuration):
    ports,devices=layout.flatten(layout.circuits(unit.schematic()),unit.NAME)
    g=layout.Geometry();uses=[];connections={n:[] for n in [*ports,'CAP']}
    centers=configuration['mos_centers']+configuration['cap_centers'];placed=[]
    def local(n):return n.replace(unit.NAME+'__','')
    for i,(device,(cx,cy)) in enumerate(zip(devices,centers)):
        cell,info=library[layout.primitive_key(device)];bb=info['bbox']
        uses.append((cell,f'I{i}',round(cx/layout.GRID),round(cy/layout.GRID),[round(v/layout.GRID) for v in bb]))
        pins={n:(layer,x+cx,y+cy) for n,(layer,x,y) in info['ports'].items()}
        placed.append(pins)
        if i>=3:continue
        nets=dict(zip(['D','G','S','B'],map(local,device['nodes'])))
        for pin in ['B','D','G','S']:
            _,px,py=pins[pin];track=cx+configuration['tracks'][pin]
            if pin=='B':
                g.pad('locali',px,py,.33);g.pad('viali',px,py,.17);g.pad('metal1',px,py,.4)
            if pin=='G':
                new_y=py+configuration['gate_escape'];g.wire('metal1',px,py,px,new_y,.18);py=new_y
            g.wire('metal1',px,py,track,py,.18);g.via12(track,py)
            connections[nets[pin]].append((track,py))
    # C1 top plates escape on M4 ABOVE each entire bottom plate before a via
    # descends to M3. All M2 drops may pass below MIM, with no accidental via.
    for i,net,target in [(3,'CAP',configuration['mos_centers'][0][0]+configuration['tracks']['S']),
                         (4,'ENB',configuration['mos_centers'][1][0]+configuration['tracks']['G'])]:
        _,x,y=placed[i]['C1'];escape=configuration['cap_escape_y']
        g.wire('metal4',x,y,x,escape,.6);g.wire('metal4',x,escape,target,escape,.6)
        g.via34(target,escape);g.via23(target,escape);connections[net].append((target,escape))
    # Each bottom plate descends locally to M2. A cross-capacitor M3 bridge
    # violates capm.11 even though both bottom plates share VSS connectivity.
    # Keep all M3 landings outside the neighboring capacitor's 1.34 um zone.
    for i,target in zip([3,4],configuration['bottom_via_x']):
        _,x,y=placed[i]['C2']
        g.wire('metal3',x,y,target,y,.4);g.via23(target,y)
        connections['VSS'].append((target,y))
    public={};labels=[]
    for net,points in connections.items():
        y=configuration['buses'][net]
        width=configuration['power_width'] if net in ['VDD','VSS'] else configuration['signal_width']
        left=configuration['bus_left'] if net in ports else min(x for x,_ in points)-.2
        right=configuration['bus_right'] if net in ports else max(x for x,_ in points)+.2
        g.wire('metal3',left,y,right,y,width)
        for x,start_y in points:
            g.wire('metal2',x,start_y,x,y,configuration['drop_width']);g.via23(x,y)
        labels.append((net,left,y,ports.index(net)+1 if net in ports else None))
        if net in ports:public[net]=dict(layer='metal3',x_um=left,y_um=y,width_um=width)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():
        lines.append(f'<< {layer} >>');lines.extend('rect '+' '.join(map(str,r)) for r in rects)
    for cell,instance,x,y,bb in uses:
        lines += [f'use {cell} {instance}','timestamp 0',f'transform 1 0 {x} 0 1 {y}','box '+' '.join(map(str,bb))]
    lines.append('<< labels >>')
    for net,x,y,port in labels:
        x=round(x/layout.GRID);y=round(y/layout.GRID)
        lines.append(f'rlabel metal3 {x} {y} {x} {y} 0 {net if port else unit.NAME+"__"+net}')
        if port:lines.append(f'port {port} nsew')
    lines.append('<< end >>')
    (out/(unit.NAME+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(unit.NAME+'.sch.spice')).write_text(layout.schematic_text(unit.NAME,ports,devices))
    return dict(ports=public,devices=len(devices),configuration=configuration,qualified_phy=False)
