# SPDX-License-Identifier: GPL-3.0-only
"""Canonical post-mux graph and placement feasibility; no timing admission."""
from collections import Counter
from copy import deepcopy
import re
import bank_floorplan_v49 as floor
import regenerated_bank_physical_v57 as seed
import tg_bank_physical_netlist_v45 as original
from build_compound_drivers_v3 import cell_definition
from native_bank_inventory_v51 import native_leaves,exact_number

FINE='openlvds_fine_moscap_w126_far_v114'
PAIR='openlvds_parallel_inv8_registered_v114'
DRIVER='openlvds_parallel_inv8_v110'


def name(copies):
    if copies not in (1,2):raise ValueError('Only one or two physical root copies supported')
    return f'openlvds_post_mux_r{copies}_placement_v118'


def graph(before,copies):
    g=deepcopy(before);g['top']=name(copies)
    if len(g['cells'])!=156:raise ValueError('Require complete original physical graph')
    old=[c for c in g['cells'] if c['name']=='u_input_inverse']
    if len(old)!=1 or old[0]['model']!=floor.INV:raise ValueError('Original input inverter missing')
    g['cells']=[c for c in g['cells'] if c['name']!='u_input_inverse']
    fine=set();driver=0
    for c in g['cells']:
        c['pins']={p:'IN' if n=='tap0' else n for p,n in c['pins'].items()}
        if c['name']=='u_fine_driver':
            if c['model']!=floor.INV or c['pins']!=dict(A='selected',Y='OUT',VGND='VGND',VPWR='VPWR'):
                raise ValueError('Original final inverter changed')
            c.update(name='u_bank_regenerator',native_name='Xbank_regenerator')
            c['pins']['Y']='fine_slow';driver+=1
        if c['model']==floor.FINE:
            match=re.fullmatch(r'u_fine_unit(\d+)',c['name'])
            if match is None:raise ValueError('Unexpected fine component')
            k=int(match[1]);fine.add(k)
            if c['pins']!=dict(A='OUT',CTRL=f'fine{k}',CTRL_B=f'fine_b{k}',VPWR='VPWR',VGND='VGND'):
                raise ValueError('Fine data/control/body wiring changed')
            c['model']=FINE;c['pins']['A']='fine_slow'
    if fine!=set(range(31)) or driver!=1:raise ValueError('Incomplete post-mux graph conversion')
    g['cells'].append(dict(name='u_fine_compound',native_name='Xfine_compound',model=PAIR,
                           pins=dict(A='fine_slow',Y='OUT',VPWR='VPWR',VGND='VGND')))
    for k in range(4):
        roots=[c for c in g['cells'] if c['name']==f'u_switch1_0_{k}']
        if len(roots)!=1 or roots[0]['model']!=floor.TG or roots[0]['pins']!=dict(A=f'tree0_{k}',Z='selected',EN=f'en1_{k}',ENB=f'en_b1_{k}',VPWR='VPWR',VGND='VGND'):
            raise ValueError('Original root mux changed')
        if copies==2:
            c=deepcopy(roots[0]);c.update(name=f'u_root_parallel{k}',native_name=f'Xroot_parallel{k}');g['cells'].append(c)
    used={c['model'] for c in g['cells']}
    g['orders']={m:p for m,p in g['orders'].items() if m in used}
    g['orders'][FINE]=['A','CTRL','CTRL_B','VPWR','VGND'];g['orders'][PAIR]=['A','Y','VPWR','VGND']
    g['physical_pin_aliases']={FINE:dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND'),PAIR:dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND')}
    if len(g['cells'])!=156+4*(copies-1):raise ValueError('Post-mux functional count changed')
    return g


def compare_component(g,text,top):
    defs=original.native.definitions(text);ports,body=defs[top]
    if ports!=g['ports']:raise ValueError('Component/physical public interface differs')
    calls={};unit=top+'_unit'
    for w in body:
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1];nodes=w[1:end-1]
        if w[0] in calls:raise ValueError('Duplicate component instance')
        if model==original.MIM:
            if w[0]!='Xtail_termination' or dict(x.split('=',1) for x in w[end:])!=dict(w='2',l='2'):
                raise ValueError('Native tail primitive changed')
            model=original.TAIL;pins=dict(zip(['A','VGND'],nodes))
        else:
            if end!=len(w) or model not in defs:raise ValueError('Unexpected component hierarchy')
            pins=dict(zip(defs[model][0],nodes))
            if model==unit:
                model=FINE;pins={dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')[p]:n for p,n in pins.items()}
            elif model==DRIVER:
                model=PAIR;pins={dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND')[p]:n for p,n in pins.items()}
        calls[w[0]]=(model,pins)
    expected={c['native_name']:(c['model'],c['pins']) for c in g['cells']}
    if len(expected)!=len(g['cells']) or calls!=expected:raise ValueError('Canonical physical graph differs from measured component calls')
    return dict(exact_component_calls_and_named_pins_verified=True,components=len(expected),qualified_phy=False)


def native_source(g,old_library,views,records):
    library={m:cell_definition(old_library,m) for m in g['orders'] if m not in (FINE,PAIR)}
    for text in views:
        for model in original.native.definitions(text):
            block=cell_definition(text,model)
            if model in library and library[model]!=block:raise ValueError('Conflicting native reference definition')
            library[model]=block
    rows=['.subckt '+g['top']+' '+' '.join(g['ports'])]
    for c in g['cells']:
        if set(c['pins'])!=set(records[c['model']]['pins']):raise ValueError('Canonical graph/master interface differs')
        rows.append(c['native_name']+' '+' '.join(c['pins'][p] for p in g['orders'][c['model']])+' '+c['model'])
    return ''.join(library[m] for m in sorted(library))+'\n'.join(rows+['.ends '+g['top'],''])


def dimension_inventory(text,top):
    _,devices=native_leaves(text,top)
    return Counter((d['model'],exact_number(d['params']['w']),exact_number(d['params']['l'])) for d in devices)


def fine_alignment(old,new):
    if set(old['pins'])!=set(new['pins']):raise ValueError('Fine public interface changed')
    shift=old['pins']['A']['anchor_um'][1]-new['pins']['A']['anchor_um'][1]
    for pin in old['pins']:
        a=old['pins'][pin]['anchor_um'];b=new['pins'][pin]['anchor_um']
        if abs(a[0]-b[0])>1e-6 or abs(a[1]-b[1]-shift)>1e-6:
            raise ValueError('Fine controls/supplies do not align with the data rail')
    return floor.q(shift)


def placement(before,g,records,copies):
    old=seed.placement(before,seed.graph(before),records);p=deepcopy(old)
    byname={c['name']:c for c in g['cells']};old_driver=p['placements'].pop('u_fine_driver')
    p['cells']=[byname.get(c['name'],c) for c in old['cells'] if c['name'] in byname or c.get('role')=='physical_support']
    p['placements']={n:xy for n,xy in p['placements'].items() if n in {c['name'] for c in p['cells']}}
    p['cells'] += [byname['u_bank_regenerator'],byname['u_fine_compound']]
    p['placements']['u_bank_regenerator']=old_driver
    fine_shift=fine_alignment(records[floor.FINE],records[FINE])
    for k in range(31):
        # Preserve every global public rail; the new capacitor row extends
        # below the old footprint rather than moving controls and power.
        p['placements'][f'u_fine_unit{k}'][1]=floor.q(p['placements'][f'u_fine_unit{k}'][1]+fine_shift)
    y=old_driver[1]+records[floor.INV]['pins']['Y']['anchor_um'][1]
    last=p['placements']['u_fine_unit30'];x=last[0]+records[FINE]['size_um'][0]+.6
    p['placements']['u_fine_compound']=[floor.q(x),floor.q(y-records[PAIR]['pins']['A']['anchor_um'][1])]
    for k in range(4):
        if copies==2:
            c=byname[f'u_root_parallel{k}'];p['cells'].append(c)
            xx,yy=p['placements'][f'u_switch1_0_{k}']
            p['placements'][c['name']]=[floor.q(xx-records[floor.TG]['size_um'][0]-.3),yy]
    p['fixed_routes']=[r for r in p['fixed_routes'] if r['net'] in ('VPWR','VGND')]
    a=records[floor.INV]['pins']['Y']['shapes'][0][1];b=records[PAIR]['pins']['A']['shapes'][0][1]
    dx,dy=p['placements']['u_fine_compound']
    p['fixed_routes'].append(dict(net='fine_slow',layer='met3',rect=[floor.q(old_driver[0]+a[0]),floor.q(old_driver[1]+a[1]),floor.q(dx+b[2]),floor.q(dy+b[3])]))
    _,out_rect=records[PAIR]['pins']['Y']['shapes'][0]
    p['ports']['OUT']=dict(layer='met3',rect=[floor.q(dx+out_rect[0]),floor.q(dy+out_rect[1]),floor.q(dx+out_rect[0]+.2),floor.q(dy+out_rect[3])])
    p['die']=[0.,0.,floor.upward(max(p['placements'][c['name']][0]+records[c['model']]['size_um'][0] for c in p['cells'])+6,floor.SITE),
              floor.upward(max(p['placements'][c['name']][1]+records[c['model']]['size_um'][1] for c in p['cells'])+6,floor.ROW)]
    for k,pin in enumerate(('VPWR','VGND')):
        xx=p['die'][2]-3;yy=p['die'][3]-3-5.44*k;p['ports'][pin]['rect']=[floor.q(xx-1.5),floor.q(yy-1.5),floor.q(xx+1.5),floor.q(yy+1.5)]
    p['boxes']=floor.validate(p['cells'],p['placements'],records,p['die']);floor.validate_groups(p['cells'],p['placements'],records,p['tapped_groups'])
    p.update(functional_instances=len(g['cells']),critical_chain=['u_switch0_0_0','u_switch1_0_0','u_bank_regenerator','u_fine_compound'],
             complete_bank_interconnect_qualified=False,routed=False,qualified_phy=False)
    return p


def fixed_bus_audit(path,g,p,records):
    import klayout.db as db
    import build_tg_bank_floorplan_v49 as assembly
    lib=db.Layout();lib.read(str(path));top=lib.cell(g['top'])
    metal=assembly.audit.region(lib,top,(70,20));result={}
    for route in p['fixed_routes']:
        net=route['net'];connected=metal.interacting(db.Region(db.Box(*[round(v/lib.dbu) for v in route['rect']]))).merged()
        if connected.count()!=1:raise ValueError('Fixed bus is not one physical metal component')
        touched=set()
        for c in p['cells']:
            dx,dy=[round(v/lib.dbu) for v in p['placements'][c['name']]]
            for pin,data in records[c['model']]['pins'].items():
                for layer,rect in data['shapes']:
                    if layer!='met3':continue
                    shape=db.Region(db.Box(*[round(v/lib.dbu) for v in rect]).transformed(db.Trans(dx,dy)))
                    if (shape&connected).is_empty():continue
                    if c['pins'][pin]!=net:raise ValueError('Fixed bus shorts another native net')
                    if not (shape-connected).is_empty():raise ValueError('Fixed bus touches only part of a native rail')
                    touched.add((c['name'],pin))
        required={(f'u_fine_unit{k}','A' if net=='fine_slow' else net) for k in range(31)}
        if net=='fine_slow':required|={('u_bank_regenerator','Y'),('u_fine_compound','A')}
        if not required<=touched:raise ValueError('Fixed bus misses required native rails')
        result[net]=dict(one_physical_metal_component=True,required_native_rails_connected=len(required),other_named_nets_shorted=False)
    return result
