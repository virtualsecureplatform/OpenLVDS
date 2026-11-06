# SPDX-License-Identifier: GPL-3.0-only
"""Exact native isolated fine-stage graph, placement and fixed-bus witnesses."""
from copy import deepcopy
import balanced_physical_graph_v126 as original
import bank_floorplan_v49 as floor
from audit_rc_comments_v2 import collapse
from build_compound_drivers_v3 import cell_definition

DRIVER='openlvds_discharge_p20n16_registered_v236'
BUFFER='openlvds_buf_8_o4_registered_v236'
TOP='openlvds_isolated_fine_physical_v239'
COMPONENT='openlvds_discharge_isolated_fine_v220'


def graph(before):
    g=deepcopy(before)
    if len(g['cells'])!=179:raise ValueError('Require original complete b2 graph')
    old=[c for c in g['cells'] if c['name']=='u_fine_compound']
    if len(old)!=1 or old[0]['model']!=original.PAIR or old[0]['pins']!=dict(A='selected',Y='OUT',VGND='VGND',VPWR='VPWR'):
        raise ValueError('Original final compound changed')
    g['cells']=[c for c in g['cells'] if c['name']!='u_fine_compound']
    for k in range(31):
        cells=[c for c in g['cells'] if c['name']==f'u_fine_unit{k}']
        if len(cells)!=1 or cells[0]['model']!=original.FINE or cells[0]['pins']!=dict(A='selected',CTRL=f'fine{k}',CTRL_B=f'fine_b{k}',VPWR='VPWR',VGND='VGND'):
            raise ValueError('Native fine programming connections changed')
        cells[0]['pins']['A']='fine_node'
    g['cells'] += [dict(name='u_fine_isolate',native_name='Xfine_isolate',model=DRIVER,pins=dict(A='selected',Y='fine_node',VGND='VGND',VPWR='VPWR')),
                   dict(name='u_fine_regenerate',native_name='Xfine_regenerate',model=BUFFER,pins=dict(A='fine_node',X='OUT',VGND='VGND',VPWR='VPWR'))]
    g['top']=TOP;g['orders'].update({DRIVER:['A','Y','VPWR','VGND'],BUFFER:['A','X','VPWR','VGND']})
    g['physical_pin_aliases'].update({m:{p:p for p in g['orders'][m]} for m in (DRIVER,BUFFER)})
    return g


def compare_component(g,text):
    defs=original.old.native.definitions(text);ports,body=defs[COMPONENT]
    if ports!=g['ports']:raise ValueError('Isolated bank public interface differs')
    aliases={
        'openlvds_measured_gangs_b2_v125_unit':(original.FINE,g['physical_pin_aliases'][original.FINE]),
        original.PAIR_SOURCE:(original.PAIR,g['physical_pin_aliases'][original.PAIR]),
        'openlvds_parallel_coarse_b2_v120':(original.coarse('b2'),g['physical_pin_aliases'][original.coarse('b2')]),
        'openlvds_discharge_p20n16_v218':(DRIVER,g['physical_pin_aliases'][DRIVER]),
        'openlvds_buf_8_o4_shunted_v2':(BUFFER,g['physical_pin_aliases'][BUFFER]),
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
    if len(expected)!=180 or calls!=expected:raise ValueError('Physical graph differs from native isolated component bank')
    return dict(exact_component_calls_and_named_pins_verified=True,components=180,qualified_phy=False)


def inventory_proof(g,reference,component):
    physical=original.dimension_inventory(reference,g['top'])
    collapsed=''.join(collapse(cell_definition(component,m)) for m in original.old.native.definitions(component))
    if physical!=original.dimension_inventory(collapsed,COMPONENT):raise ValueError('Isolated component/native physical dimensions differ')
    mos=sum(n for (m,w,l),n in physical.items() if 'fet_' in m)
    mim=sum(n for (m,w,l),n in physical.items() if 'cap_mim' in m)
    if (mos,mim)!=(1479,43):raise ValueError('Isolated bank native census changed')
    return dict(native_dimensions_and_inventory_preserved=True,native_mos=mos,native_mims=mim,qualified_phy=False)


def placement(before,g,records):
    p=deepcopy(before);supports=[c for c in p['cells'] if c.get('role')=='physical_support']
    p['cells']=[*g['cells'],*supports];p['placements'].pop('u_fine_compound')
    # Preserve all coarse/mux/selector placements. Move the complete fine
    # array and its tapped control rows by exactly 49 HD placement sites.
    dx=floor.q(49*floor.SITE)
    shifted={f'u_fine_unit{k}' for k in range(31)}
    for group in p['tapped_groups']:
        if group['name'].startswith('fine'):
            group['origin_um'][0]=floor.q(group['origin_um'][0]+dx);shifted.update(group['cells'])
    for n in shifted:p['placements'][n][0]=floor.q(p['placements'][n][0]+dx)
    for k in range(31):p['ports'][f'E{k}']['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(p['ports'][f'E{k}']['rect'])]
    x,y=before['placements']['u_fine_compound'];driver_y=before['placements']['u_fine_unit0'][1]
    p['placements']['u_fine_isolate']=[x,driver_y]
    p['placements']['u_fine_regenerate']=[floor.q(x+records[DRIVER]['size_um'][0]+.6),y]
    bx,by=p['placements']['u_fine_regenerate'];a=records[BUFFER]['pins']['A']['shapes'][0][1]
    fine=records[original.FINE]['pins']['A']['shapes'][0][1];last=p['placements']['u_fine_unit30']
    fixed=[]
    for route in before['fixed_routes']:
        route=deepcopy(route)
        if route['net']=='selected':
            route['net']='fine_node';route['rect']=[floor.q(bx+a[0]),floor.q(by+a[1]),floor.q(last[0]+fine[2]),floor.q(by+a[3])]
        else:route['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(route['rect'])]
        fixed.append(route)
    p['fixed_routes']=fixed
    r=records[BUFFER]['pins']['X']['shapes'][0][1]
    p['ports']['OUT']=dict(layer='met3',rect=[floor.q(bx+r[0]),floor.q(by+r[1]),floor.q(bx+r[0]+.2),floor.q(by+r[3])])
    p['die'][2]=floor.q(p['die'][2]+dx)
    for pin in ('VPWR','VGND'):p['ports'][pin]['rect']=[floor.q(v+dx) if j%2==0 else v for j,v in enumerate(p['ports'][pin]['rect'])]
    p['boxes']=floor.validate(p['cells'],p['placements'],records,p['die'])
    floor.validate_groups(p['cells'],p['placements'],records,p['tapped_groups'])
    p.update(functional_instances=180,critical_chain=['u_switch0_0_0','u_group_compound0','u_switch1_0_0','u_fine_isolate','u_fine_regenerate'],
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
        if net=='fine_node':required.add(('u_fine_regenerate','A'))
        if not required<=touched:raise ValueError('Fixed bus misses a required native rail')
        result[net]=dict(one_physical_metal_component=True,required_native_rails_connected=len(required),other_named_nets_shorted=False)
    return result
