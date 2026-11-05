# SPDX-License-Identifier: GPL-3.0-only
"""One public output for stronger, internally tapped native coarse buffer stages."""
import bank_floorplan_v49 as floor
from build_compound_drivers_v3 import cell_definition

INV = 'openlvds_buf_4_pair_nlvt_v29'
COPIES = dict(b2=2,b3=3)
def name(profile):
    if profile not in COPIES:raise ValueError('Unknown coarse buffer profile')
    return 'openlvds_parallel_coarse_'+profile+'_v120'


def design(profile, records):
    if profile not in COPIES:
        raise ValueError('Unknown parallel output cell')
    count=COPIES[profile];top=name(profile)
    record = records[INV]
    if record.get('requires_external_taps', True):
        raise ValueError('Require internally tapped native coarse buffer')
    width, height = record['size_um']
    origin = [2., 2.]
    pitch = floor.upward(width+2., floor.GRID)
    cells = [dict(name=f'u_buffer{k}', native_name=f'Xbuffer{k}', model=INV,
                  pins=dict(A='IN', X='OUT', VPWR='VPWR', VGND='VGND')) for k in range(count)]
    graph = dict(top=top, ports=['IN', 'OUT', 'VPWR', 'VGND'], cells=cells,
                 orders={INV: ['A', 'X', 'VPWR', 'VGND']})
    places = {c['name']: [floor.q(origin[0]+k*pitch), origin[1]] for k,c in enumerate(cells)}
    ports = {}; routes = []
    for public,pin in [('IN','A'), ('OUT','X'), ('VPWR','VPWR'), ('VGND','VGND')]:
        shapes = record['pins'][pin]['shapes']
        if len(shapes)!=1 or shapes[0][0]!='met3':
            raise ValueError('Require one native M3 rail per coarse buffer port')
        rect = shapes[0][1]
        if not (0 <= rect[0] < rect[2] <= width and 0 <= rect[1] < rect[3] <= height):
            raise ValueError('Native rail outside coarse buffer footprint')
        x,y=origin
        bridge=[floor.q(x+rect[0]), floor.q(y+rect[1]),
                floor.q(x+(count-1)*pitch+rect[2]), floor.q(y+rect[3])]
        routes.append(dict(net=public, layer='met3', rect=bridge))
        ports[public]=dict(layer='met3',rect=[floor.q(x+rect[0]), floor.q(y+rect[1]),
                                            floor.q(x+rect[0]+.2), floor.q(y+rect[3])])
    for i,a in enumerate(routes):
        for b in routes[i+1:]:
            if max(a['rect'][1],b['rect'][1]) < min(a['rect'][3],b['rect'][3])+.3:
                raise ValueError('Coarse buffer port rails lack M3 clearance')
    die=[0.,0.,floor.upward(origin[0]+(count-1)*pitch+width+2.,floor.SITE),
         floor.upward(origin[1]+height+2.,floor.ROW)]
    plan=dict(cells=cells, placements=places, die=die, ports=ports,
              fixed_routes=routes, tapped_groups=[], qualified_phy=False)
    plan['boxes']=floor.validate(cells,places,records,die)
    return graph,plan


def reference(graph,library):
    if graph['top'] not in {name(p) for p in COPIES} or len(graph['cells']) not in COPIES.values():
        raise ValueError('Parallel coarse buffer graph changed')
    definition=cell_definition(library,INV)
    order=definition.splitlines()[0].split()[2:]
    if set(order)!= {'A','X','VPWR','VGND'}:
        raise ValueError('Native coarse buffer interface changed')
    rows=[]
    for c in graph['cells']:
        rows.append(c['native_name']+' '+' '.join(c['pins'][p] for p in order)+' '+INV)
    return definition+'\n.subckt '+graph['top']+' '+' '.join(graph['ports'])+'\n'+'\n'.join(rows)+'\n.ends '+graph['top']+'\n'
