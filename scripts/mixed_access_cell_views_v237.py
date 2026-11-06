# SPDX-License-Identifier: GPL-3.0-only
"""Preserve actual M3/M4 accesses while normalizing native fine-stage cells."""
import hashlib
from pathlib import Path
import re
import build_clock_cell_views_v114 as common
import physical_cell_adapter_v44 as adapter
registry=common.registry
geometry=adapter.geometry
description=adapter.description
pins_match=adapter.pins_match
translated=adapter.translated
subtract=adapter.subtract
ROUTING=adapter.ROUTING

def integration_lef(text,name,orders,directions,aliases,anchors,shift,size,keepouts,access_layers):
    info=description(text,name);pins_match(info['pins'],aliases,orders)
    hidden=[];selected={};records={}
    for source,shapes in info['pins'].items():
        target=aliases[source];x,y=anchors[source]
        candidates=[r for layer,r in shapes if layer==access_layers[source] and r[0]<=x<=r[2] and r[1]<=y<=r[3]]
        if len(candidates)!=1:raise ValueError('Require a unique designated native access rail: '+source)
        chosen=(access_layers[source],candidates[0]);removed=False
        for shape in shapes:
            if shape==chosen and not removed:removed=True
            elif shape[0] in ROUTING:hidden.append((shape[0],translated(shape[1],shift)))
        selected[target]=(chosen[0],translated(chosen[1],shift))
        records[target]=dict(direction=directions[target].upper(),use='POWER' if target=='VPWR' else 'GROUND' if target=='VGND' else 'SIGNAL',
                             shapes=[selected[target]],anchor_um=[round(x+shift[0],6),round(y+shift[1],6)])
    for match in geometry.OBS.finditer(info['block']):
        hidden += [(layer,translated(rect,shift)) for layer,rect in geometry.rectangles(match[1]) if layer in ROUTING]
    # Only existing, electrically named public M3 conductors may be exposed
    # inside a keepout. Other nets see an obstruction, including at the edge.
    additions=[]
    for layer,rect in keepouts:
        pieces=[rect]
        for pin_layer,pin in selected.values():
            if pin_layer==layer:pieces=[q for p in pieces for q in subtract(p,pin)]
        additions += [(layer,p) for p in pieces]
    rows=[f'MACRO {name}','  CLASS BLOCK ;',f'  FOREIGN {name} ;','  ORIGIN 0 0 ;',
          f'  SIZE {size[0]:.6f} BY {size[1]:.6f} ;','  SYMMETRY X Y ;']
    for pin in orders:
        r=records[pin]
        rows += [f'  PIN {pin}',f'    DIRECTION {r["direction"]} ;',f'    USE {r["use"]} ;','    PORT',
                 geometry.render(r['shapes']).rstrip(),'    END',f'  END {pin}']
    rows += ['  OBS',geometry.render(hidden+additions).rstrip(),'  END',f'END {name}','']
    result='\n'.join(rows)
    before=geometry.geometry(info['block']);after=geometry.geometry(result)
    for (layer,rect),count in before.items():
        if after[layer,translated(rect,shift)]<count:raise ValueError('Integration abstract lost original routing geometry')
    return result,records


def normalize(spec,target):
    import klayout.db as db
    lib=db.Layout();lib.read(spec['gds']);top=lib.cell(spec['source_top'])
    if top is None or lib.dbu!=.001:raise ValueError('Source native scale/top changed')
    top.name=target
    original=Path(spec['lef']).read_text()
    renamed=re.sub(r'\b'+re.escape(spec['source_top'])+r'\b',target,original)
    info=adapter.description(renamed,target);marker=registry.region(db,lib,top,adapter.MIM)
    if abs(marker.area()*lib.dbu**2-spec['mim_area_um2'])>1e-8:raise ValueError('Native guard/output MIM geometry changed')
    ox,oy=info['origin'];w,h=info['size']
    box=db.Box(round(-ox/lib.dbu),round(-oy/lib.dbu),round((w-ox)/lib.dbu),round((h-oy)/lib.dbu))
    keepouts=[]
    for polygon in marker.each_merged():
        cap=polygon.bbox()
        if cap.area()!=polygon.area():raise ValueError('Nonrectangular MIM marker')
        halo=cap.enlarged(round(adapter.M3_CLEARANCE/lib.dbu));box=box+halo
        keepouts += [('met3',halo),('met4',cap.enlarged(round(adapter.M4_CLEARANCE/lib.dbu)))]
    shift=(-box.left,-box.bottom);size=[box.width()*lib.dbu,box.height()*lib.dbu]
    anchors={}
    for pin in spec['aliases']:
        layer=spec['access_layers'][pin]
        label_index=lib.find_layer(adapter.ROUTING[layer][0],5)
        if label_index is None:raise ValueError('Missing public label layer: '+pin)
        labels=[s.text for s in top.shapes(label_index).each() if s.is_text() and s.text.string==pin]
        if len(labels)!=1:raise ValueError('Missing/ambiguous actual public port: '+pin)
        anchors[pin]=(labels[0].x*lib.dbu,labels[0].y*lib.dbu)
    ko=[(layer,tuple(round(v*lib.dbu,6) for v in (b.left+shift[0],b.bottom+shift[1],b.right+shift[0],b.top+shift[1]))) for layer,b in keepouts]
    lef,pins=integration_lef(renamed,target,spec['order'],spec['directions'],spec['aliases'],anchors,
                                    [x*lib.dbu for x in shift],size,ko,spec['access_layers'])
    todo=[top.cell_index()];seen=set();renamed_children={};tag=hashlib.sha256(target.encode()).hexdigest()[:8]
    while todo:
        index=todo.pop()
        if index in seen:continue
        seen.add(index);todo += [i.cell_index for i in lib.cell(index).each_inst()]
    for index in sorted(seen):
        child=lib.cell(index)
        if child!=top:
            old=child.name;child.name='ov114_'+tag+'_'+hashlib.sha256(old.encode()).hexdigest()[:8];renamed_children[old]=child.name
    for index in lib.layer_indexes():
        for shape in top.shapes(index).each():
            if shape.is_text() and shape.text.string in spec['aliases']:
                text=shape.text;text.string=spec['aliases'][text.string];shape.text=text
    top.transform(db.Trans(0,False,*shift))
    record=dict(size_um=size,shift_um=[v*lib.dbu for v in shift],pins=pins,aliases=spec['aliases'],
                mim_area_um2=spec['mim_area_um2'],requires_external_taps=False,kind='custom',role='functional',
                renamed_children=renamed_children,well_domain_nets={})
    return lib,top,lef,record

