# SPDX-License-Identifier: GPL-3.0-only
"""Place the checked gate tiles locally and route quiet nets above the driver."""
from collections import defaultdict
import math
from layout import Geometry, GRID, pcell_info, schematic_text
from driver_finger_banks import mos
from probe_driver_finger_pcells import key
from build_driver_inverter_tiles import inverter_pairs


def save(out, name, g, uses, ports):
    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rects in g.layers.items():
        lines += [f'<< {layer} >>']
        lines += ['rect ' + ' '.join(map(str, r)) for r in rects]
    for cell, instance, x, y, bb in uses:
        lines += [f'use {cell} {instance}', 'timestamp 0',
                  f'transform 1 0 {round(x/GRID)} 0 1 {round(y/GRID)}',
                  'box ' + ' '.join(str(round(v/GRID)) for v in bb)]
    lines += ['<< labels >>']
    for i, (pin, v) in enumerate(ports.items(), 1):
        x,y = round(v['x_um']/GRID), round(v['y_um']/GRID)
        lines += [f'rlabel {v["layer"]} {x} {y} {x} {y} 0 {pin}', f'port {i} nsew']
    (out / (name + '.mag')).write_text('\n'.join(lines + ['<< end >>', '']))


def passive(out, name, cell, device):
    info = pcell_info(out / (cell + '.mag'))
    bb, p, g, public = info['bbox'], info['ports'], Geometry(), {}
    cap = 'cap_mim' in device['model']
    for pin in (['C1', 'C2'] if cap else ['R1', 'R2', 'B']):
        _, x, y = p[pin]
        ex = bb[0] - 3. if pin in ['C1', 'R1', 'B'] else bb[2] + 3.
        if cap:
            g.wire('metal4' if pin == 'C1' else 'metal3', x,y,ex,y,.8)
            if pin == 'C1': g.via34(ex,y)
        else:
            if pin == 'B':
                g.pad('locali',x,y,.33); g.pad('viali',x,y,.17); g.pad('metal1',x,y,.4)
                ey = bb[1] - 2.
                g.wire('metal1',x,y,x,ey,.18)
                y = ey
            g.wire('metal1',x,y,ex,y,.18)
            g.via12(ex,y); g.via23(ex,y)
        g.pad('metal3',ex,y,.6)
        public[pin] = dict(layer='metal3', x_um=ex, y_um=y)
    save(out,name,g,[(cell,'I0',0.,0.,bb)],public)
    return dict(name=name, info=pcell_info(out/(name+'.mag')))


def via45(g,x,y):
    # Drawing dimensions from pinned sky130A.tech: via4 >=1.18 um,
    # metal5 width/spacing >=1.6 um. Use 5 um track pitch below.
    g.pad('metal4',x,y,1.8); g.pad('via4',x,y,1.18); g.pad('metal5',x,y,1.8)


def write(out, top, ports, original, grouped, bank_library, tile_library, passives):
    g, uses, placements, ends = Geometry(), [], [], defaultdict(list)
    consumed = set()
    pairs = inverter_pairs(grouped)
    pair_by_name = {p['name']:(p,n) for p,n in pairs}
    rows = defaultdict(list)
    direct = set()
    used_tracks = set()

    def place(cell, nodes, pin_order, cursor, cy, members, row):
        info = pcell_info(out/(cell+'.mag'))
        bb = info['bbox']
        x = round((cursor-bb[0])/GRID)*GRID
        cy = round(cy/GRID)*GRID
        ident = 'I' + str(len(uses))
        uses.append((cell,ident,x,cy,bb))
        bound = [bb[0]+x,bb[1]+cy,bb[2]+x,bb[3]+cy]
        rows[row].append(bound)
        placements.append(dict(instance=ident,cell=cell,bbox_um=bound,members=members,row=row))
        for pin, net in zip(pin_order,nodes):
            _,px,py = info['ports'][pin]
            ends[net].append(dict(x=px+x,y=py+cy,pin=pin,bbox=bound,row=row))
        return bound[2]+28.

    def tile(pair,cursor,cy,row):
        p,n = pair
        cell = tile_library[tuple(key(x) for x in pair)]['name']
        consumed.update([p['name'],n['name']])
        return place(cell,[p['nodes'][1],p['nodes'][0],p['nodes'][2],n['nodes'][2]],
                     ['A','Y','VP','VN'],cursor,cy,p['members']+n['members'],row)

    def device(d,cursor,cy,row):
        consumed.add(d['name'])
        cell = bank_library[key(d)]['name'] if mos(d) else passives[d['name']]['name']
        pins = ['D','G','S','B'] if mos(d) else ['C1','C2'] if 'cap_mim' in d['model'] else ['R1','R2','B']
        return place(cell,d['nodes'],pins,cursor,cy,d['members'],row)

    def named(fragment):
        matches = [d for d in grouped if fragment in d['name']]
        if len(matches)!=1: raise ValueError('Nonunique physical device '+fragment)
        return matches[0]

    # The three 1.8 V frontend inverters are adjacent, with original AD/AB
    # fanout retained. Upper/lower data branches use identical placement.
    cursor = 0.
    for fragment in ['__XIN0__XP_', '__XIN1__XP_', '__XI__XP_']:
        cursor = tile(pair_by_name[named(fragment)['name']],cursor,0.,'frontend')
    branch_x = cursor + 12.
    for branch, cy in [(0,80.),(1,-80.)]:
        row = 'branch'+str(branch)
        cml = named('__XNA0_' if branch==0 else '__XNB0_')
        cursor = device(cml,branch_x,cy,row)
        for i in range(2):
            r = named(f'__XR{"L" if branch==0 else "R"}{i}')
            device(r,branch_x+i*18.,cy+25.,row)
        for stage in range(3):
            pair = pair_by_name[named(f'__XB{branch}_S{stage}_0__XP_')['name']]
            cursor = tile(pair,cursor,cy,row)
            if stage<2: direct.add(pair[0]['nodes'][0])
        # Put the small DP/DN capacitor beside the last gate tile, and the
        # bridge devices and output MIM in the same local branch channel.
        device(named('__XCDP' if branch==0 else '__XCDN'),cursor-25.,cy+45.,row)
        for fragment in (['__XPR_', '__XNR_'] if branch==0 else ['__XPL_', '__XNL_']):
            cursor = device(named(fragment),cursor,cy,row)
        device(named('__XCOUTN' if branch==0 else '__XCOUTP'),cursor,cy,row)

    # Quiet bias/CMFB/current-mirror devices occupy separate rows, keeping
    # their routing away from the short gate-to-gate connections.
    remaining = [d for d in grouped if d['name'] not in consumed]
    cursor = 0.
    for i,d in enumerate(remaining):
        if i==9: cursor=0.
        cursor = device(d,cursor,-190.-120.*(i//9),'quiet'+str(i//9))
    if consumed != {d['name'] for d in grouped}:
        raise ValueError('Missing original physical bank/device')
    members = [n for p in placements for n in p['members']]
    if sorted(members) != sorted(d['name'] for d in original):
        raise ValueError('Original finger identity changed during placement')

    routes = []
    for net in sorted(direct):
        points = ends.pop(net)
        if len(points)!=2 or points[0]['y']!=points[1]['y']:
            raise ValueError('Gate chain is not a local horizontal connection')
        a,b = points
        g.wire('metal3',a['x'],a['y'],b['x'],b['y'],.8)
        routes.append(dict(net=net,kind='direct_metal3',length_um=abs(a['x']-b['x'])))
    overall = [min(b[0] for b in uses_bounds(placements)),min(b[1] for b in uses_bounds(placements)),
               max(b[2] for b in uses_bounds(placements)),max(b[3] for b in uses_bounds(placements))]
    top_y = math.ceil(overall[3]+15.)
    local_count = defaultdict(int)
    public = {}
    net_order = list(ports)+sorted(set(ends)-set(ports))
    for net in net_order:
        points = ends[net]
        supply = net in ['VDDIO','VDDD','VSS']
        width = 5. if supply else 2. if net in ['OUTP','OUTN'] else .8
        rowset = {p['row'] for p in points}
        if len(rowset)==1 and next(iter(rowset)).startswith('branch') and net not in ports:
            row = next(iter(rowset))
            bus_y = math.ceil(max(b[3] for b in rows[row])+8.)+3.*local_count[row]
            local_count[row] += 1
        else:
            top_y += width/2 + 2.
            bus_y = top_y
            top_y += width/2 + 2.
        xs=[]
        for point in points:
            x,y = point['x'],point['y']
            left = point['pin'] in ['A','G','B','R1','C1']
            # Each M5 drop gets a globally distinct x coordinate, including
            # across rows. Its M3 landing lies outside its child geometry.
            edge = point['bbox'][0 if left else 2]
            track = math.floor((edge-5.)/5.) if left else math.ceil((edge+5.)/5.)
            while track in used_tracks: track += -1 if left else 1
            used_tracks.add(track)
            ex = track*5.
            g.wire('metal3',x,y,ex,y,.8)
            g.via34(ex,y); via45(g,ex,y)
            g.wire('metal5',ex,y,ex,bus_y,3. if supply else 1.6)
            via45(g,ex,bus_y)
            xs.append(ex)
        g.wire('metal4',min(xs)-2.,bus_y,max(xs)+2.,bus_y,width)
        routes.append(dict(net=net,kind='metal4_bus_metal5_drops',bus_y_um=bus_y,
                           horizontal_um=max(xs)-min(xs),connections=len(points)))
        if net in ports:
            public[net]=dict(layer='metal4',x_um=min(xs)-2.,y_um=bus_y,width_um=width)
    # Preserve public terminal order even when the net routing order changes.
    public = {n:public[n] for n in ports}
    save(out,top,g,uses,public)
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,original))
    return dict(ports=public,placements=placements,routes=routes,devices=len(original),
                width_um=overall[2]-overall[0],height_um=top_y-overall[1],
                original_finger_names=members)


def uses_bounds(placements):
    return [x['bbox_um'] for x in placements]
