# SPDX-License-Identifier: GPL-3.0-only
"""Keep each DLL delay section's high-impedance routing inside a local island."""
from collections import Counter
import re
from layout import GRID, Geometry, draw_macro, primitive_key


def partition(devices, ports):
    groups = {name: [] for name in ['control','delay0','delay1','delay2','delay3','replica']}
    for device in devices:
        match = re.search(r'__XL__X([0-3])__',device['name'])
        group = 'delay'+match[1] if match else ('replica' if '__XREPL__' in device['name'] else 'control')
        groups[group].append(device)
    if any(not group for group in groups.values()): raise ValueError('Expected control and five delay sections')
    signatures = [Counter(primitive_key(d) for d in groups[n]) for n in groups if n!='control']
    if any(s!=signatures[0] for s in signatures): raise ValueError('Delay section device geometries differ')
    nets={name:{n for d in group for n in d['nodes']} for name,group in groups.items()}
    counts=Counter(n for group in nets.values() for n in group)
    shared=sorted(n for n,count in counts.items() if count>1)
    public={name:[p for p in ports if p in net]+[p for p in shared if p in net and p not in ports]
            for name,net in nets.items()}
    if set(ports)-set(counts): raise ValueError('Unconnected control port')
    for name in groups:
        if name=='control': continue
        internal={n for n in nets[name] if re.search(r'__(?:N|S|B|PCTRL|T|F)$',n)}
        if internal & set(public[name]): raise ValueError('Delay internal node escaped its local island')
    return groups,public,shared


def draw(out,top,ports,devices,library):
    from layout_dll_candidate import bounds
    groups,public,shared=partition(devices,ports)
    children={};cursor=100.;ceiling=0.
    for name,group in groups.items():
        cell='local_'+name; scratch='openlvds_dll_analog'
        if (out/(scratch+'.mag')).exists(): raise ValueError('Capture each child before routing the next')
        info=draw_macro(out,scratch,public[name],group,library)
        for suffix in ['.mag','.sch.spice']:
            (out/(scratch+suffix)).replace(out/(cell+suffix))
        bb=bounds(out/(cell+'.mag'));xy=(cursor-bb[0],10.-bb[1])
        ceiling=max(ceiling,bb[3]+xy[1]);children[name]=dict(cell=cell,info=info,bbox=bb,xy=xy)
        cursor+=bb[2]-bb[0]+110.
    geometry=Geometry();labels=[];pin_map={};y=ceiling+20.;positions={}
    for name,child in children.items():
        ox,oy=child['xy']
        positions[name]={net:dict(pin,x_um=pin['x_um']+ox,y_um=pin['y_um']+oy)
                         for net,pin in child['info']['ports'].items()}
    for i,net in enumerate(shared):
        width=5. if net in ['VDDD','VSS','VDDIO'] else .4;y+=width/2+1.4;ends=[]
        for name,child in children.items():
            if net not in positions[name]: continue
            pin=positions[name][net];x=pin['x_um']
            if pin['layer']=='metal3':
                x=child['xy'][0]+child['bbox'][0]-10.-4.*i
                geometry.wire('metal3',x,pin['y_um'],pin['x_um'],pin['y_um'],width)
                geometry.via34(x,pin['y_um'])
            elif pin['layer']!='metal4': raise ValueError('Expected local child ports on metal3 or metal4')
            geometry.wire('metal4',x,pin['y_um'],x,y,.6);geometry.via34(x,y);ends.append(x)
        geometry.wire('metal3',min(ends),y,max(ends),y,width)
        labels.append((net,min(ends),y,ports.index(net)+1 if net in ports else None,'metal3'))
        if net in ports: pin_map[net]=dict(layer='metal3',x_um=min(ends),y_um=y,width_um=width)
        y+=width/2+1.4
    for net in ports:
        if net in pin_map: continue
        locations=[p[net] for p in positions.values() if net in p]
        if len(locations)!=1: raise ValueError('Invalid local control port ownership')
        pin=locations[0];pin_map[net]=pin
        labels.append((net,pin['x_um'],pin['y_um'],ports.index(net)+1,pin['layer']))
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():
        lines+=['<< '+layer+' >>']+['rect '+' '.join(map(str,r)) for r in rects]
    for child in children.values():
        x,cy=[round(v/GRID) for v in child['xy']]
        lines += [f'use {child["cell"]} {child["cell"]}','timestamp 0',f'transform 1 0 {x} 0 1 {cy}',
                  'box '+' '.join(str(round(v/GRID)) for v in child['bbox'])]
    lines+=['<< labels >>']
    for net,x,cy,index,layer in labels:
        x,cy=round(x/GRID),round(cy/GRID);lines.append(f'rlabel {layer} {x} {cy} {x} {cy} 0 {net}')
        if index: lines.append(f'port {index} nsew')
    lines+=['<< end >>'];(out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    return dict(ports=pin_map,width_um=cursor,height_um=y+10.,shared_nets=shared,
        delay_islands={name:dict(devices=len(groups[name]),ports=public[name]) for name in groups})
