#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Plan separated native buffer escapes; emit no counter geometry or admission."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import klayout.db as db

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'build/diagnostics/request_taper_counter_plan_v327/d8e29c7f91c15d0d'
VERSION = 'native-counter-m4-input-lift-m5-output-escape-plan-v328.1'
CONTEXT = 'counter_buffer_escape_plan_v328'
ROLES = ('request_driver', 'request_driver_parallel', 'clock_driver', 'clock_driver_parallel')
LAYERS = dict(metal4=(71,20), metal5=(72,20))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def rect(a, b, width):
    if a[0] != b[0] and a[1] != b[1]:
        raise ValueError('Require Manhattan escape')
    return [min(a[0],b[0])-width/2, min(a[1],b[1])-width/2,
            max(a[0],b[0])+width/2, max(a[1],b[1])+width/2]


def routes(identity):
    plan = identity['plan']; cells = {c['name']:c for c in identity['cells']}
    shapes = []; custom = []; connections = {}
    def add(net, layer, a, b, width, kind, cell=None):
        row = dict(net=net,layer=layer,rect=rect(a,b,width),kind=kind,cell=cell)
        shapes.append(row)
        if kind.startswith('buffer_'): custom.append(row)
    for net, ends in plan['points'].items():
        for end in ends:
            cell = cells[end['cell']]; macro = identity['macros'][cell['model']]
            pin = macro['row']['ports'][end['pin']]; pos = plan['placements'][cell['name']]
            px, py = pos['x']+pin['x_um'], pos['y']+pin['y_um']; tx = end['x']
            power = net in ('VGND','VPWR')
            cy = py
            if cell['name'] in ROLES and end['pin'] in ('A','X'):
                if pin['layer'] != 'metal4': raise ValueError('Require actual M4 buffer ports')
                if end['pin'] == 'A':
                    cy = pos['y']+macro['bbox'][3]+2.
                    add(net,'metal4',(px,py),(px,cy),.3,'buffer_input_lift',cell['name'])
                    add(net,'metal4',(px,cy),(tx,cy),.3,'buffer_input_escape',cell['name'])
                else:
                    # Move the long M5 track down 2um; keep its left via pad
                    # clear of the nearby global RCLK bus and landing pads.
                    cy = py-2.
                    for layer in LAYERS:
                        add(net,layer,(px,py),(px,py),2.2,'buffer_output_via4_landing',cell['name'])
                        add(net,layer,(tx,cy),(tx,cy),2.2,'buffer_output_spine_via4_landing',cell['name'])
                    add(net,'metal5',(px,py),(px,cy),1.6,'buffer_output_drop',cell['name'])
                    add(net,'metal5',(px,cy),(tx,cy),1.6,'buffer_output_escape',cell['name'])
                connections[cell['name']+'.'+end['pin']] = dict(net=net,x_um=tx,y_um=cy,
                    native_port_x_um=px,native_port_y_um=py,
                    via4_cut_um=1.8 if end['pin']=='X' else None)
            else:
                if pin['layer'] == 'metal3':
                    rail = [r for layer,r in macro['lef']['pins'][end['pin']] if layer=='met3'
                            and r[0]<=pin['x_um']<=r[2] and r[1]<=pin['y_um']<=r[3]]
                    if len(rail)!=1: raise ValueError('Ambiguous original native M3 rail')
                    if not power:
                        px = pos['x']+rail[0][2]-3.-2*list(cell['pins']).index(end['pin'])
                    add(net,'metal4',(px,py),(px,py),.6 if power else .4,'old_native_landing',cell['name'])
                elif pin['layer'] != 'metal4': raise ValueError('Unsupported native port layer')
                add(net,'metal4',(px,py),(tx,py),.6 if power else .3,'old_escape',cell['name'])
            add(net,'metal4',(tx,cy),(tx,cy),.6 if power else .4,'spine_landing',cell['name'])
        by = plan['buses'][net]
        for tx in sorted({end['x'] for end in ends}):
            for layer in LAYERS:
                add(net,layer,(tx,by),(tx,by),plan['configuration']['via4_pad_um'],'global_via4_landing')
        xs = [end['x'] for end in ends]
        left = .3 if net in ('RCLK','REQUEST','PREPARE','RESET_N','VGND','VPWR','CLK') else min(xs)-1.4
        add(net,'metal5',(left,by),(max(xs)+1.4,by),2. if net in ('VGND','VPWR') else 1.6,'global_bus')
    return dict(shapes=shapes,buffer_shapes=custom,spine_connections=connections,
                via4_cut_um=1.8,via4_pad_um=2.2,m5_width_um=1.6)


def different_net_overlaps(shapes):
    conflicts=[]
    for k,a in enumerate(shapes):
        for b in shapes[k+1:]:
            if a['net']==b['net'] or a['layer']!=b['layer']:continue
            x,y=a['rect'],b['rect']
            if min(x[2],y[2])>max(x[0],y[0])+1e-9 and min(x[3],y[3])>max(x[1],y[1])+1e-9:
                conflicts.append(dict(first=a,second=b))
    return conflicts


def native_mask_check(identity, proposed):
    """Reject buffer additions touching any foreign native M4/M5 polygon.

    A native merged polygon touching an actual same-net M4 public port is
    allowed; all other native polygons are forbidden. This checks contact,
    not minimum spacing, vias, other layers, complete connectivity or DRC.
    """
    libraries={}; observed=0
    for cell in identity['cells']:
        model=cell['model']; macro=identity['macros'][model]
        if model not in libraries:
            lib=db.Layout();lib.read(str(ROOT/macro['folder']/(model+'.gds')))
            libraries[model]=(lib,lib.cell(model))
        lib,top=libraries[model]; pos=identity['plan']['placements'][cell['name']]
        translate=db.Trans(round(pos['x']/lib.dbu),round(pos['y']/lib.dbu))
        for layer,number in LAYERS.items():
            native=db.Region(top.begin_shapes_rec(lib.layer(*number))).merged().transformed(translate)
            for shape in proposed['buffer_shapes']:
                if shape['layer']!=layer:continue
                allowed=db.Region()
                for pin,net in cell['pins'].items():
                    port=macro['row']['ports'][pin]
                    if net!=shape['net'] or port['layer']!=layer:continue
                    x=round((pos['x']+port['x_um'])/lib.dbu);y=round((pos['y']+port['y_um'])/lib.dbu)
                    allowed += native.interacting(db.Region(db.Box(x-1,y-1,x+1,y+1)))
                addition=db.Region(db.Box(*[round(v/lib.dbu) for v in shape['rect']]))
                if not (addition & (native-allowed)).is_empty():
                    raise ValueError('Buffer escape touches foreign native '+layer+' in '+cell['name']+': '+shape['kind'])
                observed+=1
    return dict(native_component_instances=len(identity['cells']),native_master_types=len(libraries),
                buffer_shape_native_layer_checks=observed,foreign_native_m4_m5_contacts=0)


def run():
    manifest=json.loads((PARENT/'manifest.json').read_text());i=manifest['identity']
    if (PARENT.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((PARENT/'state.json').read_text())!=dict(status='complete',planning_completed=True,qualified_phy=False)
            or any(sha(ROOT/n if not Path(n).is_absolute() else Path(n))!=h for n,h in i['inputs'].items())):
        raise ValueError('Require unchanged complete native floorplan materials')
    proposed=routes(i);conflicts=different_net_overlaps(proposed['shapes'])
    if conflicts:raise ValueError('Different-net planned M4/M5 contacts: '+repr(conflicts[:2]))
    masks=native_mask_check(i,proposed)
    paths=[Path(__file__),*[PARENT/n for n in ('manifest.json','summary.json','state.json')]]
    inputs={**i['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    record=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,proposed=proposed)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=record,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(**masks,different_net_planned_m4_m5_contacts=0,
        escape_plan_contact_checks_passed=True,native_geometry_built=False,counter_timing_qualified=False,
        shared_wire_rc_qualified=False,qualified_phy=False,
        scope='Proposed M4 input lift/M5 output escape contact checks against native masks and planned M4/M5 bus/landing rectangles only; no complete spacing/via/DRC/LVS/RC/timing/PVT/PHY admission'),indent=2)+'\n')
    (out/'state.json').write_text('{"status":"complete","planning_completed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    print(run(),flush=True)
