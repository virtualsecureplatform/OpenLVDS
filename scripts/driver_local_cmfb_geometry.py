# SPDX-License-Identifier: GPL-3.0-only
"""Keep the CMFB OTA and its high-impedance routing in the quiet analog rows."""
import math
import driver_compact_geometry as baseline
from layout import Geometry,GRID


def analog_first(grouped,top):
    fragments=['__XCM__XNP_','__XCM__XNM_','__XCM__XNT_','__XCM__XPL_','__XCM__XPR_',
               '__XRCP','__XRCN','__XRCM0','__XRCM1']
    chosen=[]
    for fragment in fragments:
        matches=[d for d in grouped if (fragment in d['name'] if fragment.startswith('__XCM__') else d['name']==top+fragment)]
        if len(matches)!=1: raise ValueError('Require one original analog group '+fragment)
        chosen.append(matches[0])
    names={d['name'] for d in chosen}
    return chosen+[d for d in grouped if d['name'] not in names]


def load_geometry(path):
    lines=path.read_text().splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('use '))
    g=Geometry();layer=None
    for line in lines[:start]:
        if line.startswith('<< '):layer=line.split()[1]
        elif line.startswith('rect '):g.layers[layer].append(list(map(int,line.split()[1:])))
    return g,lines[start:]


def remove_all(rectangles,expected):
    count=rectangles.count(expected)
    if not count: raise ValueError('Original routing shape missing during CMFB localization')
    rectangles[:]=[r for r in rectangles if r!=expected]
    return count


def relocate_bus(g,old_y,new_y,placements):
    """Keep terminal landings and unique M5 columns; replace only their bus end."""
    old=round(old_y/GRID);half=round(.8/GRID)
    stems=[r for r in g.layers['metal5'] if r[2]-r[0]==2*half and r[3]==old+half and r[1]<old-half]
    if not stems: raise ValueError('Require original quiet-net M5 stems')
    for child in placements:
        if child['bbox_um'][1]-1.2<new_y<child['bbox_um'][3]+1.2:
            raise ValueError('Localized CMFB bus crosses child geometry')
    xs=sorted({(r[0]+r[2])*GRID/2 for r in stems})
    expected=Geometry();expected.wire('metal4',min(xs)-2.,old_y,max(xs)+2.,old_y,.8)
    remove_all(g.layers['metal4'],expected.layers['metal4'][0])
    for x in xs:
        pads=Geometry();baseline.via45(pads,x,old_y)
        for layer,rects in pads.layers.items():
            for rect in rects:remove_all(g.layers[layer],rect)
    for rect in stems:
        # Different pins can share a same-net column. Retain every original
        # terminal endpoint and remove all duplicate source rectangles.
        if rect not in g.layers['metal5']:continue
        x=(rect[0]+rect[2])*GRID/2;start=(rect[1]+half)*GRID
        remove_all(g.layers['metal5'],rect)
        g.wire('metal5',x,start,x,new_y,1.6)
    for x in xs:baseline.via45(g,x,new_y)
    g.wire('metal4',min(xs)-2.,new_y,max(xs)+2.,new_y,.8)
    return dict(old_bus_y_um=old_y,bus_y_um=new_y,horizontal_um=max(xs)-min(xs),columns=len(xs))


def write(out,top,ports,original,grouped,bank_library,tile_library,passives):
    reordered=analog_first(grouped,top)
    info=baseline.write(out,top,ports,original,reordered,bank_library,tile_library,passives)
    quiet=[p for p in info['placements'] if p['row'].startswith('quiet')]
    first=[p for p in quiet if p['row']=='quiet0']
    if len(first)!=9 or sorted(n for p in first for n in p['members'])!=sorted(n for d in reordered[:9] for n in d['members']):
        raise ValueError('Require the original nine CMFB/sense groups together in the first quiet row')
    path=out/(top+'.mag');g,tail=load_geometry(path)
    names=[top+'__XCM__L',top+'__XCM__T',top+'__CM',top+'__CMS',top+'__SINK']
    top_y=max(p['bbox_um'][3] for p in quiet)
    local_y=math.ceil(top_y+8.);changes=[]
    for index,net in enumerate(names):
        route=[r for r in info['routes'] if r['net']==net]
        if len(route)!=1 or route[0]['kind']!='metal4_bus_metal5_drops':
            raise ValueError('Missing original CMFB net bus '+net)
        changed=relocate_bus(g,route[0]['bus_y_um'],local_y+3.*index,info['placements'])
        changes.append(dict(net=net,**changed));route[0].update(changed,kind='local_analog_metal4_bus_metal5_drops')
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():
        lines += [f'<< {layer} >>']+['rect '+' '.join(map(str,r)) for r in rects]
    path.write_text('\n'.join(lines+tail)+'\n')
    info['local_cmfb_routes']=changes
    info['analog_first_groups']=[d['name'] for d in reordered[:9]]
    info['scope']='Identical source, original MOS fingers and PDK passives; local CMFB placement/routing trial only.'
    return info


# The original passive wrappers are unchanged and independently rechecked
# as part of the new complete macro's DRC/LVS.
passive=baseline.passive
