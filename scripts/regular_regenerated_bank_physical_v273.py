# SPDX-License-Identifier: GPL-3.0-only
"""Named-pin graph and placement for the regular-inverter regenerator pair."""
from copy import deepcopy
import isolated_fine_bank_physical_v239 as previous
from build_compound_drivers_v3 import cell_definition
from audit_rc_comments_v2 import collapse

original=previous.original
floor=previous.floor
DRIVER=previous.DRIVER
TOP='openlvds_regular_regenerated_physical_v273'
COMPONENT='openlvds_regular_regenerated_fine_v263'
SHIFT_SITES=52


def graph(before):
    g=deepcopy(before)
    old=[c for c in g['cells'] if c['name']=='u_fine_regenerate']
    if (len(g['cells'])!=180 or len(old)!=1 or old[0]['model']!=previous.BUFFER
        or old[0]['pins']!=dict(A='fine_node',X='OUT',VGND='VGND',VPWR='VPWR')):
        raise ValueError('Require original native isolated regenerator graph')
    g['cells']=[c for c in g['cells'] if c['name']!='u_fine_regenerate']
    for k,a,y in ((0,'fine_node','restored_b'),(1,'restored_b','OUT')):
        g['cells'].append(dict(name=f'u_fine_regenerate{k}',native_name=f'Xfine_regenerate{k}',model=DRIVER,
                              pins=dict(A=a,Y=y,VGND='VGND',VPWR='VPWR')))
    if any(c['model']==previous.BUFFER for c in g['cells']):raise ValueError('Unexpected extra output-buffer use')
    g['orders'].pop(previous.BUFFER);g['physical_pin_aliases'].pop(previous.BUFFER)
    g['top']=TOP;return g


def compare_component(g,text):
    defs=original.old.native.definitions(text);ports,body=defs[COMPONENT]
    if ports!=g['ports']:raise ValueError('Regular-pair component public interface differs')
    aliases={
        'openlvds_measured_gangs_b2_v125_unit':(original.FINE,g['physical_pin_aliases'][original.FINE]),
        original.PAIR_SOURCE:(original.PAIR,g['physical_pin_aliases'][original.PAIR]),
        'openlvds_parallel_coarse_b2_v120':(original.coarse('b2'),g['physical_pin_aliases'][original.coarse('b2')]),
        'openlvds_discharge_p20n16_v218':(DRIVER,g['physical_pin_aliases'][DRIVER]),
    }
    calls={}
    for w in body:
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1];nodes=w[1:end-1]
        if w[0] in calls:raise ValueError('Duplicate component instance')
        if model==original.old.MIM:
            if w[0]!='Xtail_termination' or dict(t.split('=',1) for t in w[end:])!=dict(w='2',l='2'):
                raise ValueError('Native balancing tail changed')
            model=original.old.TAIL;pins=dict(zip(['A','VGND'],nodes))
        else:
            if end!=len(w) or model not in defs or len(nodes)!=len(defs[model][0]):raise ValueError('Unknown native component interface')
            pins=dict(zip(defs[model][0],nodes))
            if model in aliases:
                model,rename=aliases[model];pins={rename[p]:n for p,n in pins.items()}
        calls[w[0]]=(model,pins)
    expected={c['native_name']:(c['model'],c['pins']) for c in g['cells']}
    if len(expected)!=181 or calls!=expected:raise ValueError('Physical graph differs from native regular-pair bank')
    return dict(exact_component_calls_and_named_pins_verified=True,components=181,qualified_phy=False)


def reference(g,corrected):
    defs=original.old.native.definitions(corrected)
    if any(defs[model][0]!=order for model,order in g['orders'].items()):
        raise ValueError('Corrected native definition port order differs from graph')
    return original.native_source(g,[corrected])


def inventory_proof(g,reference,component):
    physical=original.dimension_inventory(reference,g['top'])
    collapsed=''.join(collapse(cell_definition(component,m)) for m in original.old.native.definitions(component))
    if physical!=original.dimension_inventory(collapsed,COMPONENT):raise ValueError('Regular-pair native physical dimensions differ')
    mos=sum(n for (m,w,l),n in physical.items() if 'fet_' in m)
    mim=sum(n for (m,w,l),n in physical.items() if 'cap_mim' in m)
    if (mos,mim)!=(1529,43):raise ValueError('Regular-pair native census changed')
    return dict(native_dimensions_and_inventory_preserved=True,native_mos=mos,native_mims=mim,qualified_phy=False)


def placement(before,g,records):
    p=deepcopy(before);supports=[c for c in p['cells'] if c.get('role')=='physical_support']
    p['cells']=[*g['cells'],*supports];p['placements'].pop('u_fine_regenerate')
    dx=floor.q(SHIFT_SITES*floor.SITE);shifted={f'u_fine_unit{k}' for k in range(31)}
    for group in p['tapped_groups']:
        if group['name'].startswith('fine'):
            group['origin_um'][0]=floor.q(group['origin_um'][0]+dx);shifted.update(group['cells'])
    for name in shifted:p['placements'][name][0]=floor.q(p['placements'][name][0]+dx)
    for k in range(31):p['ports'][f'E{k}']['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(p['ports'][f'E{k}']['rect'])]
    x=before['placements']['u_fine_regenerate'][0];y=before['placements']['u_fine_isolate'][1]
    for k in (0,1):p['placements'][f'u_fine_regenerate{k}']=[floor.q(x+k*(records[DRIVER]['size_um'][0]+.6)),y]
    for route in p['fixed_routes']:
        route['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(route['rect'])]
        if route['net']=='fine_node':
            first=p['placements']['u_fine_unit0'];pin=records[original.FINE]['pins']['A']['shapes'][0][1]
            route['rect'][0]=floor.q(first[0]+pin[0])
    # Both new stages have actual M4 input/output rails. Their local nets
    # remain unrouted here; the fixed M3 fanout touches the 31 fine cells.
    bx,by=p['placements']['u_fine_regenerate1'];ax,ay=records[DRIVER]['pins']['Y']['anchor_um']
    p['ports']['OUT']=dict(layer='met4',rect=[floor.q(bx+ax-.1),floor.q(by+ay-.1),floor.q(bx+ax+.1),floor.q(by+ay+.1)])
    p['die'][2]=floor.q(p['die'][2]+dx)
    for pin in ('VPWR','VGND'):p['ports'][pin]['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(p['ports'][pin]['rect'])]
    p['boxes']=floor.validate(p['cells'],p['placements'],records,p['die'])
    floor.validate_groups(p['cells'],p['placements'],records,p['tapped_groups'])
    p.update(functional_instances=181,critical_chain=['u_switch0_0_0','u_group_compound0','u_switch1_0_0','u_fine_isolate','u_fine_regenerate0','u_fine_regenerate1'],
        whole_bank_lvs_passed=False,root_outputs_routed=False,routed=False,qualified_phy=False)
    return p


def fixed_bus_audit(path,g,p,records):
    import klayout.db as db
    import build_tg_bank_floorplan_v49 as assembly
    lib=db.Layout();lib.read(str(path));top=lib.cell(g['top']);metal=assembly.audit.region(lib,top,(70,20));result={}
    for route in p['fixed_routes']:
        net=route['net'];connected=metal.interacting(db.Region(db.Box(*[round(v/lib.dbu) for v in route['rect']]))).merged()
        if connected.count()!=1:raise ValueError('Fine fixed bus is not one actual metal component')
        touched=set()
        for c in p['cells']:
            dx,dy=[round(v/lib.dbu) for v in p['placements'][c['name']]]
            for pin,data in records[c['model']]['pins'].items():
                for layer,rect in data['shapes']:
                    if layer!='met3':continue
                    shape=db.Region(db.Box(*[round(v/lib.dbu) for v in rect]).transformed(db.Trans(dx,dy)))
                    if (shape&connected).is_empty():continue
                    if c['pins'][pin]!=net:raise ValueError('Fixed bus shorts a different named terminal')
                    if not (shape-connected).is_empty():raise ValueError('Fixed bus only partially touches a native pin')
                    touched.add((c['name'],pin))
        required={(f'u_fine_unit{k}','A' if net=='fine_node' else net) for k in range(31)}
        if not required<=touched:raise ValueError('Fixed bus misses a required native rail')
        result[net]=dict(one_physical_metal_component=True,required_native_rails_connected=len(required),other_named_nets_shorted=False)
    return result
