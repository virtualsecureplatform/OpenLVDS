# SPDX-License-Identifier: GPL-3.0-only
"""Placement feasibility for measured balanced-bank gangs, without admission."""
from copy import deepcopy
import bank_floorplan_v49 as floor
import regenerated_bank_physical_v57 as seed
import balanced_physical_graph_v126 as graph_model
from post_mux_bank_physical_v118 import fine_alignment


def placement(before,g,records,profile):
    old=seed.placement(before,seed.graph(before),records)
    byname={c['name']:c for c in g['cells']}
    supports=[c for c in old['cells'] if c.get('role')=='physical_support']
    cells=[*g['cells'],*supports];names={c['name'] for c in cells}
    places={n:deepcopy(xy) for n,xy in old['placements'].items() if n in names}
    p=deepcopy(old);p['cells']=cells;p['placements']=places
    fine=graph_model.FINE;pair=graph_model.PAIR;coarse=graph_model.coarse(profile)
    tg=floor.TG;tw,th=records[tg]['size_um'];pw,ph=records[pair]['size_um'];bw,bh=records[coarse]['size_um']
    # Four taps per row, with unchanged row heights and serpentine chain.
    start=2.18;pitch=floor.upward(bw+1.6,floor.GRID);top_y=old['placements']['u_delay1'][1]
    for index in range(16):
        row,col=divmod(index,4);col=3-col if row%2==0 else col
        tag=f'u_delay{index+1}' if index<15 else 'u_tail_load'
        places[tag]=[floor.q(start+col*pitch),floor.q(top_y-row*(bh+1.))]
    tail=places['u_tail_load'];tail_record=records[graph_model.old.TAIL]
    places['u_tail_termination']=[floor.q(tail[0]+bw+.6),floor.q(tail[1]+records[coarse]['pins']['X']['anchor_um'][1]-tail_record['pins']['A']['anchor_um'][1])]
    # Two copies of each leaf in a four-column/two-row group. Each branch
    # has one paired-inverter macro and two root TGs. No cells are reflected.
    left=2.18;base_y=28.2;leaf_pitch=floor.upward(tw+.3,floor.GRID)
    row_pitch=floor.upward(th+1.8,floor.GRID);group_pitch=floor.upward(2*row_pitch,floor.GRID)
    gx=left+3*leaf_pitch+tw+.6;rx=gx+pw+.3
    for group in range(4):
        y=base_y+group*group_pitch
        for leaf in range(4):
            row,col=divmod(leaf,2)
            for copy,tag in [(0,f'u_switch0_{group}_{leaf}'),(1,f'u_leaf_parallel{group}_{leaf}')]:
                places[tag]=[floor.q(left+(2*col+copy)*leaf_pitch),floor.q(y+row*row_pitch)]
        input_y=y+records[tg]['pins']['Z']['anchor_um'][1]
        gy=input_y-records[pair]['pins']['A']['anchor_um'][1]
        places[f'u_group_compound{group}']=[floor.q(gx),floor.q(gy)]
        root_y=gy+records[pair]['pins']['Y']['anchor_um'][1]-records[tg]['pins']['A']['anchor_um'][1]
        places[f'u_switch1_0_{group}']=[floor.q(rx),floor.q(root_y)]
        places[f'u_root_parallel{group}']=[floor.q(rx+leaf_pitch),floor.q(root_y)]
    root_right=rx+leaf_pitch+tw
    coarse_right=start+3*pitch+bw
    first=max(root_right+2.+pw+.6,coarse_right+3.)
    data_y=old['placements']['u_fine_unit0'][1]+records[floor.FINE]['pins']['A']['anchor_um'][1]
    shift=fine_alignment(records[floor.FINE],records[fine]);fine_y=old['placements']['u_fine_unit0'][1]+shift
    fine_pitch=floor.upward(records[fine]['size_um'][0]+.2,floor.GRID)
    dx=first-old['placements']['u_fine_unit0'][0]
    for k in range(31):places[f'u_fine_unit{k}']=[floor.q(first+k*fine_pitch),floor.q(fine_y)]
    for group in p['tapped_groups']:
        if not group['name'].startswith('fine'):continue
        k=int(group['name'][4:]);old_x=group['origin_um'][0];new_x=floor.upward(old_x+dx,floor.SITE);delta=new_x-old_x
        group['origin_um'][0]=new_x
        for n in group['cells']:places[n][0]=floor.q(places[n][0]+delta)
        p['ports'][f'E{k}']['rect']=[floor.q(v+delta) if i%2==0 else v for i,v in enumerate(p['ports'][f'E{k}']['rect'])]
    final=[floor.q(first-.6-pw),floor.q(data_y-records[pair]['pins']['A']['anchor_um'][1])]
    places['u_fine_compound']=final
    # The selected bus connects all fine NODE rails and final A. The eight
    # root Z terminals remain explicitly unrouted, as do controls/supplies.
    fixed=[]
    for net in ['VPWR','VGND']:
        r=records[fine]['pins'][net]['shapes'][0][1];last=places['u_fine_unit30']
        fixed.append(dict(net=net,layer='met3',rect=[floor.q(first+r[0]),floor.q(fine_y+r[1]),floor.q(last[0]+r[2]),floor.q(fine_y+r[3])]))
    a=records[pair]['pins']['A']['shapes'][0][1];b=records[fine]['pins']['A']['shapes'][0][1]
    fixed.append(dict(net='selected',layer='met3',rect=[floor.q(final[0]+a[0]),floor.q(final[1]+a[1]),floor.q(places['u_fine_unit30'][0]+b[2]),floor.q(final[1]+a[3])]))
    p['fixed_routes']=fixed
    for public,tag,pin in [('IN','u_switch0_0_0','A'),('OUT','u_fine_compound','Y')]:
        x,y=places[tag];r=records[byname[tag]['model']]['pins'][pin]['shapes'][0][1]
        p['ports'][public]=dict(layer='met3',rect=[floor.q(x+r[0]),floor.q(y+r[1]),floor.q(x+r[0]+.2),floor.q(y+r[3])])
    p['die']=[0.,0.,floor.upward(max(places[c['name']][0]+records[c['model']]['size_um'][0] for c in cells)+6,floor.SITE),
              floor.upward(max(places[c['name']][1]+records[c['model']]['size_um'][1] for c in cells)+6,floor.ROW)]
    for k,pin in enumerate(['VPWR','VGND']):
        x=p['die'][2]-3;y=p['die'][3]-3-5.44*k;p['ports'][pin]['rect']=[floor.q(x-1.5),floor.q(y-1.5),floor.q(x+1.5),floor.q(y+1.5)]
    p['boxes']=floor.validate(cells,places,records,p['die']);floor.validate_groups(cells,places,records,p['tapped_groups'])
    p.update(functional_instances=179,critical_chain=['u_switch0_0_0','u_group_compound0','u_switch1_0_0','u_fine_compound'],
             input_requires_routing=True,root_outputs_routed=False,routed=False,qualified_phy=False)
    return p


def fixed_bus_audit(path,g,p,records):
    import klayout.db as db
    import build_tg_bank_floorplan_v49 as assembly
    lib=db.Layout();lib.read(str(path));top=lib.cell(g['top']);metal=assembly.audit.region(lib,top,(70,20));result={}
    for route in p['fixed_routes']:
        net=route['net'];connected=metal.interacting(db.Region(db.Box(*[round(v/lib.dbu) for v in route['rect']]))).merged()
        if connected.count()!=1:raise ValueError('Balanced fixed bus is not one physical metal component')
        touched=set()
        for c in p['cells']:
            dx,dy=[round(v/lib.dbu) for v in p['placements'][c['name']]]
            for pin,data in records[c['model']]['pins'].items():
                for layer,rect in data['shapes']:
                    if layer!='met3':continue
                    shape=db.Region(db.Box(*[round(v/lib.dbu) for v in rect]).transformed(db.Trans(dx,dy)))
                    if (shape&connected).is_empty():continue
                    if c['pins'][pin]!=net:raise ValueError('Balanced fixed bus shorts another named terminal')
                    if not (shape-connected).is_empty():raise ValueError('Balanced bus touches only part of a native rail')
                    touched.add((c['name'],pin))
        required={(f'u_fine_unit{k}','A' if net=='selected' else net) for k in range(31)}
        if net=='selected':required.add(('u_fine_compound','A'))
        if not required<=touched:raise ValueError('Balanced fixed bus misses required native rails')
        result[net]=dict(one_physical_metal_component=True,required_native_rails_connected=len(required),other_named_nets_shorted=False)
    return result
