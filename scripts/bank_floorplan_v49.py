# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic both2 placement with local well-tapped control rows."""
import math

INV='openlvds_inv_8_nlvt_o2_v34'
TG='openlvds_tg_quad_stacked_nlvt_v27'
FINE='openlvds_mim_switch_2x3_v2'
SC='sky130_fd_sc_hd__'
TAP=SC+'tapvpwrvgnd_1'
FILL=SC+'fill_1'
SITE=.46
ROW=2.72
GRID=.005


def q(x):return round(x,6)


def upward(x,pitch):return q(math.ceil((x-1e-9)/pitch)*pitch)


def validate(cells,places,records,die):
    if len({c['name'] for c in cells})!=len(cells) or set(places)!={c['name'] for c in cells}:
        raise ValueError('Missing or duplicate placed bank instance')
    boxes={}
    for c in cells:
        x,y=places[c['name']];w,h=records[c['model']]['size_um']
        if any(abs(v/GRID-round(v/GRID))>1e-6 for v in (x,y,w,h)):
            raise ValueError('Placement is off manufacturing grid')
        if c['model'].startswith(SC) and (abs(x/SITE-round(x/SITE))>1e-6 or abs(y/ROW-round(y/ROW))>1e-6):
            raise ValueError('Standard control is off its actual site grid')
        b=[q(x),q(y),q(x+w),q(y+h)]
        if not (die[0]<=b[0]<b[2]<=die[2] and die[1]<=b[1]<b[3]<=die[3]):
            raise ValueError('Placed cell outside die: '+c['name'])
        boxes[c['name']]=b
    for n,a in boxes.items():
        for m,b in boxes.items():
            if m<=n:continue
            if max(a[0],b[0])<min(a[2],b[2])-1e-8 and max(a[1],b[1])<min(a[3],b[3])-1e-8:
                raise ValueError('Physical cell footprints overlap: '+n+'/'+m)
    return boxes


def validate_groups(cells,places,records,groups):
    byname={c['name']:c for c in cells};seen=[]
    for group in groups:
        names=group['cells'];models=[byname[n]['model'] for n in names]
        if models[0]!=FILL or models[-1]!=FILL or models.count(TAP)!=2:
            raise ValueError('Control row lacks physical boundary fillers or two well taps')
        x,y=group['origin_um']
        for name in names:
            c=byname[name]
            if not c['model'].startswith(SC) or places[name]!=[q(x),q(y)]:
                raise ValueError('Control row has a physical gap or different orientation/origin')
            w,h=records[c['model']]['size_um']
            if abs(h-ROW)>1e-8:raise ValueError('Control row height differs from physical standard cell')
            for pin,net in c['pins'].items():
                if pin in ('VPWR','VPB','VGND','VNB') and net!=('VGND' if pin in ('VGND','VNB') else 'VPWR'):
                    raise ValueError('Control well or supply mapped to wrong domain')
            x+=w
        if abs(x-group['origin_um'][0]-group['width_um'])>1e-8:raise ValueError('Control row width changed')
        seen+=names
    wanted={c['name'] for c in cells if c['model'].startswith(SC)}
    if len(set(seen))!=len(seen) or set(seen)!=wanted:
        raise ValueError('Standard cell outside its tapped physical row')


def derive(graph,records):
    cells=[dict(c) for c in graph['cells']];byname={c['name']:c for c in cells};places={};groups=[]
    if len(cells)!=156 or len(byname)!=156:raise ValueError('Require complete both2 graph')
    gap=.3;ox=48*SITE;oy=4*ROW
    def put(name,x,y):
        if name in places or name not in byname:raise ValueError('Unknown or repeated physical cell')
        places[name]=[q(x+ox),q(y+oy)]
    def anchor(model,pin):return records[model]['pins'][pin]['anchor_um']
    iw,ih=records[INV]['size_um'];tw,th=records[TG]['size_um'];fw,fh=records[FINE]['size_um']
    put('u_input_inverse',0,20)
    signal_y=20+anchor(INV,'Y')[1];tg_y=signal_y-anchor(TG,'A')[1]
    x0=iw+gap;x1=x0+tw+gap;xd=x1+tw+gap;yd=signal_y-anchor(INV,'A')[1]
    put('u_switch0_0_0',x0,tg_y);put('u_switch1_0_0',x1,tg_y);put('u_fine_driver',xd,yd)
    pitch=upward(th+1.8,GRID)
    for k in range(1,4):
        put(f'u_switch0_0_{k}',x0,tg_y+k*pitch)
        put(f'u_switch1_0_{k}',x1,tg_y+k*pitch)
    for group in range(1,4):
        for k in range(4):put(f'u_switch0_{group}_{k}',xd+(group-1)*(tw+gap),tg_y+2*pitch+k*pitch)
    xf=xd+iw+gap;yf=yd+anchor(INV,'Y')[1]-anchor(FINE,'A')[1]
    fine_pitch=upward(fw+.2,GRID)
    # The first coarse load remains beside the input inverter. A serpentine
    # chain beneath it avoids a long tap0 branch to an isolated coarse row.
    buffer=byname['u_delay1']['model'];bw,bh=records[buffer]['size_um'];coarse_gap=1.6
    coarse_left=5.36-3*(bw+coarse_gap)
    for index in range(16):
        row,col=divmod(index,4);col=3-col if row%2==0 else col
        put(f'u_delay{index+1}' if index<15 else 'u_tail_load',coarse_left+col*(bw+coarse_gap),15-row*(bh+1.0))
    put('u_tail_termination',5.36+bw+.3,0)
    def standard_group(tag,names,x,y):
        x=upward(x+ox,SITE);y=upward(y+oy,ROW);start=x;members=[]
        for slot,model in [('fill_l',FILL),('tap_l',TAP),*[(name,byname[name]['model']) for name in names],('tap_r',TAP),('fill_r',FILL)]:
            if slot in names:name=slot
            else:
                name='p_'+tag+'_'+slot
                pins={p:('VGND' if p in ('VGND','VNB') else 'VPWR') for p in records[model]['pins']}
                c=dict(name=name,model=model,pins=pins,role='physical_support');cells.append(c);byname[name]=c
            if name in places:raise ValueError('Repeated tapped control cell')
            places[name]=[q(x),q(y)];members.append(name);x+=records[model]['size_um'][0]
        groups.append(dict(name=tag,cells=members,origin_um=[q(start),q(y)],width_um=q(x-start)))
    for k in range(31):
        put(f'u_fine_unit{k}',xf+k*fine_pitch,yf)
        standard_group(f'fine{k}',[f'u_fine_buffer{k}',f'u_fine_inverse{k}'],xf+k*fine_pitch,13.6)
    selectors=[[f'u_select_buffer{k}',f'u_select_inverse{k}'] for k in range(4)]
    selectors += [[f'u_decode{level}_{k}',f'u_decode_inverse{level}_{k}'] for level in range(2) for k in range(4)]
    for k,names in enumerate(selectors):
        standard_group(f'select{k}',names,50+(k%4)*12,43.52+(k//4)*5.44)
    maxx=max(places[c['name']][0]+records[c['model']]['size_um'][0] for c in cells)
    maxy=max(places[c['name']][1]+records[c['model']]['size_um'][1] for c in cells)
    die=[0.,0.,upward(maxx+6,SITE),upward(maxy+6,ROW)]
    boxes=validate(cells,places,records,die)
    validate_groups(cells,places,records,groups)
    ports={}
    for port,inst,pin in [('IN','u_input_inverse','A'),('OUT','u_fine_unit0','A')]:
        px,py=places[inst];ax,ay=anchor(byname[inst]['model'],pin)
        ports[port]=dict(layer='met3',rect=[q(px+ax-.1),q(py+ay-.1),q(px+ax+.1),q(py+ay+.1)])
    for k in range(31):
        x=places[f'u_fine_buffer{k}'][0]+anchor(SC+'buf_1','A')[0]
        ports[f'E{k}']=dict(layer='met3',rect=[q(x-.4),2.42,q(x+.4),3.02])
    for k in range(4):
        x=ox+3*k
        ports[f'S{k}']=dict(layer='met3',rect=[q(x-.4),2.42,q(x+.4),3.02])
    for k,pin in enumerate(('VPWR','VGND')):
        x=die[2]-3;y=die[3]-3-5.44*k
        ports[pin]=dict(layer='met5',rect=[q(x-1.5),q(y-1.5),q(x+1.5),q(y+1.5)])
    if set(ports)!=set(graph['ports']):raise ValueError('Missing physical public pin')
    # These native rails are shared nets, so inter-cell bridges also eliminate
    # the illegal 0.2 um gaps between the boundary-wide fine supply rectangles.
    fixed=[]
    for net in ('VPWR','VGND'):
        _,r=records[FINE]['pins'][net]['shapes'][0]
        ax,ay=places['u_fine_unit0'];bx,by=places['u_fine_unit30']
        fixed.append(dict(net=net,layer='met3',rect=[q(ax+r[0]),q(ay+r[1]),q(bx+r[2]),q(by+r[3])]))
    _,r=records[INV]['pins']['Y']['shapes'][0];ax,ay=places['u_fine_driver']
    _,f=records[FINE]['pins']['A']['shapes'][0];bx,by=places['u_fine_unit30']
    fixed.append(dict(net='OUT',layer='met3',rect=[q(ax+r[0]),q(ay+r[1]),q(bx+f[2]),q(ay+r[3])]))
    return dict(cells=cells,placements=places,boxes=boxes,die=die,tapped_groups=groups,ports=ports,
                fixed_routes=fixed,coarse_buffer_column_gap_um=coarse_gap,
                functional_instances=156,physical_taps=86,physical_fillers=86,
                critical_chain=['u_input_inverse','u_switch0_0_0','u_switch1_0_0','u_fine_driver'],
                fine_pitch_um=fine_pitch,nominal_fine_rail_edge_gap_um=q(fine_pitch-fw),
                routed=False,qualified_phy=False)
