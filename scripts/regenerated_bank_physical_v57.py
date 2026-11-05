# SPDX-License-Identifier: GPL-3.0-only
"""Canonical physical graph and tapped placement for branch regeneration."""
from copy import deepcopy
import bank_floorplan_v49 as floor
import tg_bank_physical_netlist_v45 as original
from native_bank_inventory_v51 import native_leaves
from audit_rc_comments_v2 import collapse

NAME='openlvds_dcdl_c16_f32_regenerated_physical_v57'


def graph(before):
    g=deepcopy(before);g['top']=NAME
    if len(g['cells'])!=156:raise ValueError('Require complete original physical graph')
    removed=[c for c in g['cells'] if c['name']=='u_input_inverse']
    if len(removed)!=1 or removed[0]['model']!=floor.INV:raise ValueError('Original input inverter missing')
    g['cells']=[c for c in g['cells'] if c['name']!='u_input_inverse']
    for c in g['cells']:
        c['pins']={p:'IN' if n=='tap0' else n for p,n in c['pins'].items()}
    for k in range(4):
        c=next(c for c in g['cells'] if c['name']==f'u_switch1_0_{k}')
        if c['pins']['A']!=f'tree0_{k}':raise ValueError('Unexpected original root mux input')
        c['pins']['A']=f'regenerated{k}'
        g['cells'].append(dict(name=f'u_group_inverse{k}',native_name=f'Xgroup_inverse{k}',model=floor.INV,
                              pins=dict(A=f'tree0_{k}',Y=f'regenerated{k}',VGND='VGND',VPWR='VPWR')))
    return g


def native_source(g,library,component_model):
    text=''.join(original.cell_definition(library,m) for m in sorted(g['orders']))
    rows=['.subckt '+NAME+' '+' '.join(g['ports'])]
    for c in g['cells']:rows.append(c['native_name']+' '+' '.join(c['pins'][p] for p in g['orders'][c['model']])+' '+c['model'])
    result=text+'\n'.join(rows+['.ends '+NAME,''])
    if original.signature(result,NAME)!=original.signature(collapse(component_model),'openlvds_dcdl_c16_f32_regenerated_v56'):
        raise ValueError('Physical graph differs from actual regenerated component circuit')
    _,leaves=native_leaves(result,NAME)
    mos=sum('fet_' in d['model'] for d in leaves);mim=sum('cap_mim' in d['model'] for d in leaves)
    if (mos,mim)!=(951,68):raise ValueError('Regenerated physical primitive census changed')
    return result


def verilog(g):
    return original.verilog(g).replace('module '+original.NAME+' (','module '+NAME+' (',1)


def verify_json(data,g):
    # The immutable v45 checker assumes one top name. Normalize that name
    # only; no pin, connection, direction, instance or attribute is adapted.
    d=deepcopy(data);gg=deepcopy(g)
    if original.NAME in d['modules'] or NAME not in d['modules']:raise ValueError('Unexpected regenerated top hierarchy')
    d['modules'][original.NAME]=d['modules'].pop(NAME);gg['top']=original.NAME
    return original.verify_json(d,gg)


def placement(before,g,records):
    old=floor.derive(before,records);p=deepcopy(old);byname={c['name']:c for c in g['cells']}
    p['cells']=[byname.get(c['name'],c) for c in p['cells'] if c['name']!='u_input_inverse']
    p['cells'] += [c for c in g['cells'] if c['name'].startswith('u_group_inverse')]
    p['placements'].pop('u_input_inverse')
    for k in range(4):
        p['placements'][f'u_group_inverse{k}']=[22.08,floor.q(30.88+17.2*k)]
        p['placements'][f'u_switch1_0_{k}']=[34.93,floor.q(29.64+17.2*k)]
        near=17.38 if k%2==0 else 7.98
        for leaf in range(4):
            p['placements'][f'u_switch0_{k}_{leaf}']=[floor.q(near-(leaf%2)*4.7),floor.q(28.2+17.2*k+(leaf//2)*12)]
    p['placements']['u_fine_driver'][0]-=4.7
    for k in range(31):p['placements'][f'u_fine_unit{k}'][0]-=4.7
    for group in p['tapped_groups']:
        if not group['name'].startswith('fine'):continue
        group['origin_um'][0]=floor.q(group['origin_um'][0]-4.6)
        for name in group['cells']:p['placements'][name][0]=floor.q(p['placements'][name][0]-4.6)
    for c in p['cells']:
        if c['name'].startswith('u_delay') or c['name'] in ('u_tail_load','u_tail_termination'):
            p['placements'][c['name']][1]=floor.q(p['placements'][c['name']][1]-3)
    for name,xy in p['placements'].items():p['placements'][name]=[floor.q(v) for v in xy]
    p['die']=[0.,0.,floor.upward(max(p['placements'][c['name']][0]+records[c['model']]['size_um'][0] for c in p['cells'])+6,floor.SITE),
              floor.upward(max(p['placements'][c['name']][1]+records[c['model']]['size_um'][1] for c in p['cells'])+6,floor.ROW)]
    p['boxes']=floor.validate(p['cells'],p['placements'],records,p['die']);floor.validate_groups(p['cells'],p['placements'],records,p['tapped_groups'])
    # IN now drives a coarse buffer and a TG, so it needs actual routing.
    # Place a full-size on-track input access pad; do not mark IN preconnected.
    p['ports']['IN']=dict(layer='met3',rect=[18.46,27.24,19.26,27.84])
    for name,d in p['ports'].items():
        if name=='OUT':d['rect']=[floor.q(v-4.7) if j%2==0 else v for j,v in enumerate(d['rect'])]
        elif name.startswith('E'):d['rect']=[floor.q(v-4.6) if j%2==0 else v for j,v in enumerate(d['rect'])]
    for k,pin in enumerate(('VPWR','VGND')):
        x=p['die'][2]-3;y=p['die'][3]-3-5.44*k;p['ports'][pin]['rect']=[floor.q(x-1.5),floor.q(y-1.5),floor.q(x+1.5),floor.q(y+1.5)]
    for route in p['fixed_routes']:route['rect']=[floor.q(v-4.7) if j%2==0 else v for j,v in enumerate(route['rect'])]
    p.update(functional_instances=159,critical_chain=['u_switch0_0_0','u_group_inverse0','u_switch1_0_0','u_fine_driver'],
             input_requires_routing=True,routed=False,qualified_phy=False)
    return p
