# SPDX-License-Identifier: GPL-3.0-only
"""One public output for two real, internally tapped INV8 component masters."""
import bank_floorplan_v49 as floor
from build_compound_drivers_v3 import cell_definition

INV = floor.INV
TOP = 'openlvds_parallel_inv8_v110'


def design(profile, records):
    if profile != 'inv2':
        raise ValueError('Unknown parallel output cell')
    record = records[INV]
    if record.get('requires_external_taps', True):
        raise ValueError('Require internally tapped native inverter')
    width, height = record['size_um']
    origin = [2., 2.]
    pitch = floor.upward(width+1., floor.GRID)
    cells = [dict(name=f'u_inv{k}', native_name=f'Xinv{k}', model=INV,
                  pins=dict(A='IN', Y='OUT', VPWR='VPWR', VGND='VGND')) for k in range(2)]
    graph = dict(top=TOP, ports=['IN', 'OUT', 'VPWR', 'VGND'], cells=cells,
                 orders={INV: ['A', 'VGND', 'VPWR', 'Y']})
    places = {c['name']: [floor.q(origin[0]+k*pitch), origin[1]] for k,c in enumerate(cells)}
    ports = {}; routes = []
    for public,pin in [('IN','A'), ('OUT','Y'), ('VPWR','VPWR'), ('VGND','VGND')]:
        shapes = record['pins'][pin]['shapes']
        if len(shapes)!=1 or shapes[0][0]!='met3':
            raise ValueError('Require one native M3 rail per inverter port')
        rect = shapes[0][1]
        if not (0 <= rect[0] < rect[2] <= width and 0 <= rect[1] < rect[3] <= height):
            raise ValueError('Native rail outside inverter footprint')
        x,y=origin
        bridge=[floor.q(x+rect[0]), floor.q(y+rect[1]),
                floor.q(x+pitch+rect[2]), floor.q(y+rect[3])]
        routes.append(dict(net=public, layer='met3', rect=bridge))
        ports[public]=dict(layer='met3',rect=[floor.q(x+rect[0]), floor.q(y+rect[1]),
                                            floor.q(x+rect[0]+.2), floor.q(y+rect[3])])
    for i,a in enumerate(routes):
        for b in routes[i+1:]:
            if max(a['rect'][1],b['rect'][1]) < min(a['rect'][3],b['rect'][3])+.3:
                raise ValueError('Parallel port rails lack M3 clearance')
    die=[0.,0.,floor.upward(origin[0]+pitch+width+2.,floor.SITE),
         floor.upward(origin[1]+height+2.,floor.ROW)]
    plan=dict(cells=cells, placements=places, die=die, ports=ports,
              fixed_routes=routes, tapped_groups=[], qualified_phy=False)
    plan['boxes']=floor.validate(cells,places,records,die)
    return graph,plan


def reference(graph,library):
    if graph['top']!=TOP or len(graph['cells'])!=2:
        raise ValueError('Parallel inverter graph changed')
    definition=cell_definition(library,INV)
    order=definition.splitlines()[0].split()[2:]
    if set(order)!= {'A','Y','VPWR','VGND'}:
        raise ValueError('Native inverter interface changed')
    rows=[]
    for c in graph['cells']:
        rows.append(c['native_name']+' '+' '.join(c['pins'][p] for p in order)+' '+INV)
    return definition+'\n.subckt '+TOP+' '+' '.join(graph['ports'])+'\n'+'\n'.join(rows)+'\n.ends '+TOP+'\n'
