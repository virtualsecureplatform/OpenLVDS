# SPDX-License-Identifier: GPL-3.0-only
"""Pin aliases, origin normalization and MIM-aware integration abstracts."""
import re
import math
import mim_switch_abstract_v2 as geometry

ROUTING={'li1':(67,20),'met1':(68,20),'met2':(69,20),'met3':(70,20),'met4':(71,20),'met5':(72,20)}
MIM=(89,44)
M3_CLEARANCE=1.34
M4_CLEARANCE=.3


def macro(text,name):
    matches=re.findall(r'(?ms)^MACRO '+re.escape(name)+r'\s*\n.*?^END '+re.escape(name)+r'\s*$',text)
    if len(matches)!=1:raise ValueError('Missing or duplicate LEF master: '+name)
    return matches[0].rstrip()+'\n'


def description(text,name):
    block=macro(text,name)
    size=re.search(r'\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;',block)
    origin=re.search(r'\bORIGIN\s+([-\d.]+)\s+([-\d.]+)\s*;',block)
    if size is None:raise ValueError('LEF master has no size')
    pins={m[1]:geometry.rectangles(m[2]) for m in geometry.PIN.finditer(block)}
    if len(pins)!=len(list(geometry.PIN.finditer(block))):raise ValueError('Duplicate LEF pin')
    return dict(block=block,size=[float(size[1]),float(size[2])],origin=[float(origin[1]),float(origin[2])] if origin else [0.,0.],pins=pins)


def translated(rect,shift):
    return tuple(round(v+shift[i%2],6) for i,v in enumerate(rect))


def subtract(rect,cut):
    x0,y0,x1,y1=rect;a,b,c,d=cut
    a,b,c,d=max(x0,a),max(y0,b),min(x1,c),min(y1,d)
    if a>=c or b>=d:return [rect]
    return [r for r in [(x0,y0,x1,b),(x0,d,x1,y1),(x0,b,a,d),(c,b,x1,d)] if r[0]<r[2] and r[1]<r[3]]


def pins_match(pins,aliases,orders):
    if set(aliases)!=set(pins) or set(aliases.values())!=set(orders) or len(set(aliases.values()))!=len(aliases):
        raise ValueError('Physical-to-logical pin adapter is not bijective')


def integration_lef(text,name,orders,directions,aliases,anchors,shift,size,keepouts):
    info=description(text,name);pins_match(info['pins'],aliases,orders)
    hidden=[];selected={};records={}
    for source,shapes in info['pins'].items():
        target=aliases[source];x,y=anchors[source]
        candidates=[r for layer,r in shapes if layer=='met3' and r[0]<=x<=r[2] and r[1]<=y<=r[3]]
        if len(candidates)!=1:raise ValueError('Require a unique designated M3 access rail: '+source)
        chosen=('met3',candidates[0]);removed=False
        for shape in shapes:
            if shape==chosen and not removed:removed=True
            elif shape[0] in ROUTING:hidden.append((shape[0],translated(shape[1],shift)))
        selected[target]=translated(chosen[1],shift)
        records[target]=dict(direction=directions[target].upper(),use='POWER' if target=='VPWR' else 'GROUND' if target=='VGND' else 'SIGNAL',
                             shapes=[('met3',selected[target])],anchor_um=[round(x+shift[0],6),round(y+shift[1],6)])
    for match in geometry.OBS.finditer(info['block']):
        hidden += [(layer,translated(rect,shift)) for layer,rect in geometry.rectangles(match[1]) if layer in ROUTING]
    # Only existing, electrically named public M3 conductors may be exposed
    # inside a keepout. Other nets see an obstruction, including at the edge.
    additions=[]
    for layer,rect in keepouts:
        pieces=[rect]
        if layer=='met3':
            for pin in selected.values():pieces=[q for p in pieces for q in subtract(p,pin)]
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


def standard_pins(text,name,orders,directions):
    info=description(text,name);pins_match(info['pins'],{p:p for p in info['pins']},orders)
    if info['origin']!=[0.,0.]:raise ValueError('Standard-cell origin must remain unchanged')
    records={}
    for pin,shapes in info['pins'].items():
        route=[s for s in shapes if s[0] in ROUTING]
        layer,rect=(route or shapes)[0]
        records[pin]=dict(direction=directions[pin].upper(),use='POWER' if pin in ('VPWR','VPB') else 'GROUND' if pin in ('VGND','VNB') else 'SIGNAL',
                          shapes=shapes,anchor_um=[(rect[0]+rect[2])/2,(rect[1]+rect[3])/2],well_domain_only=not bool(route))
    return records


def parameter_signature(text):
    import layout
    from reduce_rc import number
    from collections import Counter
    defs=layout.circuits(text)
    if len(defs)!=1:raise ValueError('Require one flat native cell')
    _,devices=next(iter(defs.values()));result=Counter()
    for _,nodes,model,params in devices:
        p={k:number(v) for k,v in params.items()}
        if 'fet_' in model:
            if set(p)!={'w','l','ad','as','pd','ps'}:raise ValueError('Custom cell lost actual native junction parameters')
            key=(model,p['w'],p['l'],tuple(sorted(((p['ad'],p['pd']),(p['as'],p['ps'])))))
        elif model=='sky130_fd_pr__cap_mim_m3_1' and set(p)=={'w','l'}:key=(model,p['w'],p['l'])
        else:raise ValueError('Unexpected primitive in custom physical cell')
        result[key]+=1
    return result
