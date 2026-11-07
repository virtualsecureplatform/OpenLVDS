#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the boundary-passed counter with a local native 5x5 MIM shunt."""
import argparse
from collections import Counter
from copy import deepcopy
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import klayout.db as db
import layout
import preflight_shunted_counter_v343 as material
import plan_counter_buffer_escapes_v328 as escape
import verify_counter_escape_contacts_v329 as contact
import build_counter_output_mim5_v336 as capacitor
from probe_digital_dcc_v2 import atomic

ROOT = material.ROOT
VERSION = 'repaired-power-stems-m5-spacing-native-shunted-counter-physical-v345.1'
CONTEXT = 'shunted_counter_physical_v345'
NAME = 'openlvds_shunted_counter_v345'
FAILED = ROOT/'build/diagnostics/shunted_counter_physical_v344/4656736040717545'
PORTS = material.PORTS
sha = material.sha
assembly = material.legacy.assembly
SCOPE = ('Actual 23-macro counter routing with widened parallel-buffer power corridor, '
         'M3/M4/M5 native-contact checks, uniform M5 escapes and local '
         '5x5 native shunt; DRC/strict LVS/native-mask proof only, no shared-wire '
         'RC, extracted transient, all-PVT, DLL or PHY admission; completed v343 '
         'full native evidence validation is bound by receipt, historical raw '
         'waveforms are not rehashed by this geometry producer')


def route_plan(old, cells, macros):
    if cells != material.add_shunt(old['cells']):
        raise ValueError('Require exact passed 23-role shunted counter')
    result = deepcopy(old['plan'])
    places = result['placements']
    # The old clock-parallel supply stems passed through the first buffers'
    # native M3 supply/output metal. Move both parallel buffers and their
    # supply stems right together; keep every phase-logic placement unchanged.
    for role in ('request_driver_parallel','clock_driver_parallel'):
        places[role]['x']+=40.
    for net in ('VGND','VPWR'):
        for end in result['points'][net]:
            if end['cell'] in ('request_driver_parallel','clock_driver_parallel'):
                end['x']+=40.
    # Original RCLK bus at 228um had only 1.2um clearance from the native
    # request output's M5 via4 pad. The unused inter-row gap admits 234um.
    result['buses']['RCLK']=234.
    setter = next(c for c in cells if c['name'] == 'low0_set_pair')
    sm = macros[setter['model']]
    cap = macros[material.CAP]
    sy = round(places[setter['name']]['y']+sm['row']['ports']['Y']['y_um'],3)
    right = round(places[setter['name']]['x']+sm['bbox'][2],3)
    # Place in the existing gutter, adjacent to the setter's right Y rail.
    # Return ground directly to the adjacent setter rail on M5, so the
    # capacitor and setter share their local ground before the long supply stem.
    places[material.ROLE] = dict(x=round(right+3.24, 3),
        y=round(sy-cap['row']['ports']['Y']['y_um'], 3))
    if material.planning.overlaps(cells, macros, places):
        raise ValueError('Added capacitor overlaps an actual native macro')
    p = places[material.ROLE]
    ports = {n: (round(p['x']+v['x_um'],3), round(p['y']+v['y_um'],3)) for n,v in cap['row']['ports'].items()}
    if set(ports) != {'Y', 'VGND'} or abs(ports['Y'][1]-ports['VGND'][1]) > 1e-9:
        raise ValueError('Require aligned native capacitor electrode accesses')
    gp=sm['row']['ports']['VGND']
    ground_y=round(places[setter['name']]['y']+gp['y_um'],3)
    ground_rails=[r for layer,r in sm['lef']['pins']['VGND'] if layer=='met4'
                  and r[1]<=gp['y_um']<=r[3]]
    if gp['layer']!='metal4' or len(ground_rails)!=1:
        raise ValueError('Require unique native setter M4 ground rail')
    ground_x=right+1.74
    rails = [r for layer,r in sm['lef']['pins']['Y'] if layer == 'met4'
             and r[1] <= sm['row']['ports']['Y']['y_um'] <= r[3]]
    if len(rails) != 1:
        raise ValueError('Require unique native setter M4 output rail')
    anchor = (places[setter['name']]['x']+rails[0][2]-.4, sy)
    outside = (right+1.74, sy)
    shapes = []
    def add(net, layer, a, b, width, kind):
        shapes.append(dict(net=net, layer=layer, rect=escape.rect(a,b,width), kind=kind, cell=material.ROLE))
    # Retain narrow spacing beside the adjacent B and supply rails, then widen
    # in free space. The native top electrode needs no new cut through MIM.
    add('low0_sn','metal4',anchor,outside,.3,'shunt_setter_escape')
    add('low0_sn','metal4',outside,ports['Y'],.8,'shunt_top_bridge')
    gx, gy = ports['VGND']
    ground_anchor=(places[setter['name']]['x']+ground_rails[0][2]-.4,ground_y)
    add('VGND','metal4',ground_anchor,(ground_x,ground_y),.6,'shunt_local_ground_escape')
    for xy in ((gx,gy), (ground_x,ground_y)):
        for layer in escape.LAYERS:
            add('VGND',layer,xy,xy,2.2,'shunt_ground_via4_landing')
    add('VGND','metal5',(gx,gy),(gx,ground_y),2.2,'shunt_ground_drop')
    add('VGND','metal5',(gx,ground_y),(ground_x,ground_y),2.2,'shunt_local_ground_bridge')
    base = escape.routes(dict(old,plan=result))
    # Match the via landing width through the entire output bend. The old
    # 1.6um strokes beside 2.2um pads formed sub-1.6um self-notches.
    for row in base['shapes']:
        if row['kind'] in ('buffer_output_drop','buffer_output_escape'):
            x0,y0,x1,y1=row['rect']
            row['rect']=[x0-.3,y0-.3,x1+.3,y1+.3]
    base['buffer_output_width_um']=2.2
    # Include the direct feedback strokes, absent from the old escape-only plan.
    direct = []
    for wire in result['direct_feedback']:
        a,b = wire['ends']
        for xy,z,width in (((a['x_um'],a['y_um']),(a['x_um'],b['y_um']),wire['vertical_width_um']),
                           ((a['x_um'],b['y_um']),(b['x_um'],b['y_um']),wire['width_um'])):
            direct.append(dict(net=wire['net'],layer='metal4',rect=escape.rect(xy,z,width),
                               kind='direct_feedback',cell=None))
        for e in (a,b):
            xy=(e['x_um'],e['y_um'])
            direct.append(dict(net=wire['net'],layer='metal4',rect=escape.rect(xy,xy,.4),
                               kind='direct_feedback_landing',cell=e['cell']))
    all_shapes = base['shapes']+direct+shapes
    if contact.contacts(all_shapes):
        raise ValueError('Different-net M4/M5 route contact including shunt and direct feedback')
    return dict(result, base_escapes=base, shunt_shapes=shapes,
        all_m4_m5_shapes=all_shapes, ground_setter_contact=dict(x_um=ground_x,y_um=ground_y),
        cap_ground_contact=dict(x_um=gx,y_um=gy),
        shunt_connection=dict(Y='low0_sn',VGND='VGND'))


def m3_shapes(cells,macros,plan):
    """Associate every parent M3 stem and via landing with its actual net."""
    lookup={c['name']:c for c in cells};shapes=[]
    def add(net,a,b,width,kind):
        shapes.append(dict(net=net,layer='metal3',rect=escape.rect(a,b,width),kind=kind))
    for net,ends in plan['points'].items():
        power=net in ('VGND','VPWR');by=plan['buses'][net]
        for e in ends:
            c=lookup[e['cell']];m=macros[c['model']];pin=m['row']['ports'][e['pin']]
            pos=plan['placements'][c['name']];px=pos['x']+pin['x_um'];py=pos['y']+pin['y_um']
            cy=plan['base_escapes']['spine_connections'].get(c['name']+'.'+e['pin'],{}).get('y_um',py)
            add(net,(e['x'],cy),(e['x'],by),2. if power else .4,'parent_spine')
            add(net,(e['x'],cy),(e['x'],cy),.6 if power else .4,'spine_via3_landing')
            if pin['layer']=='metal3':
                rail=[r for layer,r in m['lef']['pins'][e['pin']] if layer=='met3'
                      and r[0]<=pin['x_um']<=r[2] and r[1]<=pin['y_um']<=r[3]]
                if len(rail)!=1:raise ValueError('Ambiguous native M3 access')
                if not power:px=pos['x']+rail[0][2]-3.-2*list(c['pins']).index(e['pin'])
                add(net,(px,py),(px,py),.6 if power else .4,'native_via3_landing')
        for x in {e['x'] for e in ends}:add(net,(x,by),(x,by),.6,'global_via3_landing')
    for wire in plan['direct_feedback']:
        for e in wire['ends']:
            xy=(e['x_um'],e['y_um']);add(wire['net'],xy,xy,.4,'direct_feedback_via3_landing')
    return shapes


def check_native_contacts(cells, macros, plan):
    """Check every parent M3/M4/M5 addition against foreign native masks."""
    additions=plan['all_m4_m5_shapes']+m3_shapes(cells,macros,plan)
    libraries = {}; checks = 0
    for cell in cells:
        model = cell['model']; macro = macros[model]
        if model not in libraries:
            lib=db.Layout(); lib.read(str(ROOT/macro['folder']/(model+'.gds')))
            libraries[model]=(lib,lib.cell(model))
        lib,top=libraries[model]; pos=plan['placements'][cell['name']]
        trans=db.Trans(round(pos['x']/lib.dbu),round(pos['y']/lib.dbu))
        for layer,number in dict(metal3=(70,20),**escape.LAYERS).items():
            native=capacitor.fabrication_region(lib,top,number).merged().transformed(trans)
            for shape in additions:
                if shape['layer'] != layer: continue
                allowed=db.Region()
                for pin,net in cell['pins'].items():
                    port=macro['row']['ports'][pin]
                    # The capacitor bottom port is M3 with a native via3 and
                    # M4 landing at the same C2 coordinate. Do not infer other
                    # cross-layer native electrode connections.
                    bottom = (model == material.CAP and pin == 'VGND' and layer == 'metal4'
                              and port.get('native_electrode') == 'C2' and port['layer'] == 'metal3')
                    if net != shape['net'] or (port['layer'] != layer and not bottom): continue
                    x=round((pos['x']+port['x_um'])/lib.dbu)
                    y=round((pos['y']+port['y_um'])/lib.dbu)
                    allowed += native.interacting(db.Region(db.Box(x-1,y-1,x+1,y+1)))
                extra=db.Region(db.Box(*[round(v/lib.dbu) for v in shape['rect']]))
                if not extra.interacting(native-allowed).is_empty():
                    raise ValueError('Custom routing contacts foreign native '+layer+' in '+cell['name']+': '+shape['kind'])
                checks+=1
    return dict(native_layer_contact_checks=checks,foreign_native_m3_m4_m5_contacts=0)


def electrical_texts(lib,cell):
    """Retain text content/position/orientation/presentation except font height.

    The existing tap master has identical supply labels with heights 125 and
    156 in different qualified source GDS libraries. Height draws no mask and
    changes no label connectivity. Do not ignore label names or transforms.
    """
    result=[]
    for k in lib.layer_indices():
        info=lib.get_info(k);shapes=cell.begin_shapes_rec(k)
        while not shapes.at_end():
            shape=shapes.shape()
            if shape.is_text():
                text=shape.text.transformed(shapes.trans());text.size=0
                result.append((info.layer,info.datatype,text.to_s()))
            shapes.next()
    return sorted(result)


def native_witness(macros, output=None, cells=None, places=None):
    """Compare every fabrication layer, electrical label and native hierarchy."""
    reference={}; duplicate=0; height_differences=[]
    def instances(lib,cell):
        return Counter((lib.cell(v.cell_index).name,v.cplx_trans.to_s(),v.a.x,v.a.y,v.b.x,v.b.y,v.na,v.nb)
                       for v in cell.each_inst())
    def equal(a,ca,b,cb):
        capacitor.masks_equal(a,ca,b,cb)
        if electrical_texts(a,ca)!=electrical_texts(b,cb):
            raise ValueError('Native electrical annotation changed: '+ca.name)
        if capacitor.native_texts(a,ca)!=capacitor.native_texts(b,cb):
            height_differences.append(ca.name)
        if instances(a,ca) != instances(b,cb):
            raise ValueError('Native hierarchy changed: '+ca.name)
    for name,m in sorted(macros.items()):
        lib=db.Layout(); lib.read(str(ROOT/m['folder']/(name+'.gds')))
        if lib.dbu != .001: raise ValueError('Native GDS scale changed')
        for cell in lib.each_cell():
            if cell.name in reference:
                a,ca=reference[cell.name]; equal(a,ca,lib,cell); duplicate+=1
            else: reference[cell.name]=(lib,cell)
    if output is not None:
        lib=db.Layout();lib.read(str(output))
        for name,(a,ca) in reference.items():
            cb=lib.cell(name)
            if cb is None: raise ValueError('Missing integrated native master: '+name)
            equal(a,ca,lib,cb)
        top=lib.cell(NAME)
        if top is None: raise ValueError('Missing integrated counter top')
        expected=Counter((c['model'],db.ICplxTrans(1,0,False,
            round(places[c['name']]['x']/lib.dbu),round(places[c['name']]['y']/lib.dbu)).to_s(),0,0,0,0,0,0) for c in cells)
        if instances(lib,top) != expected: raise ValueError('Integrated 23-macro placements changed')
    return dict(native_master_count=len(reference),identical_duplicate_masters=duplicate,
        all_native_masks_and_electrical_labels_preserved=True,native_hierarchy_preserved=True,
        text_height_presentation_ignored=True,text_height_difference_masters=sorted(set(height_differences)),
        integrated_macro_placements_verified=output is not None)


def prepare(parent):
    m=json.loads((parent/'manifest.json').read_text()); i=m['identity']
    r=json.loads((parent/'summary.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics'/material.CONTEXT or i['version'] != material.VERSION
            or parent.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((parent/'state.json').read_text()) != dict(status='complete',passed=True,qualified_phy=False)
            or r.get('counter_materials_compatible') is not True
            or r.get('strict_native_topology_equivalence_passed') is not True
            or r.get('all_twelve_native_boundaries_independently_replayed') is not True):
        raise ValueError('Require complete passing twelve-boundary counter integration preflight')
    # V343 has already fully revalidated all twelve native traces. Bind that
    # terminal receipt and every non-waveform input here. Historical waveforms
    # are upstream evidence, not consumed by placement, DRC or strict LVS.
    selected_inputs={n:h for n,h in i['inputs'].items() if not n.endswith('.raw')}
    if any(sha(ROOT/n) != h for n,h in selected_inputs.items()) or any(sha(parent/n) != h for n,h in r['files'].items()):
        raise ValueError('Captured native integration evidence changed')
    old=json.loads((ROOT/i['original_plan']/'manifest.json').read_text())['identity']
    cells=deepcopy(i['cells']);macros=deepcopy(i['macros'])
    plan=route_plan(old,cells,macros)
    checks=check_native_contacts(cells,macros,plan)
    witness=native_witness(macros)
    expected=material.reference(cells,macros).replace(material.NAME,NAME)
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
    if (json.loads((FAILED/'state.json').read_text()).get('status')!='failed'
            or (FAILED/'openlvds_shunted_counter_v344/openlvds_shunted_counter_v344.drc_count.txt').read_text().strip()!='18'):
        raise ValueError('Require retained original M3-short/M5-spacing physical failure')
    paths += [FAILED/n for n in ('manifest.json','state.json',
        'openlvds_shunted_counter_v344/openlvds_shunted_counter_v344.gds',
        'openlvds_shunted_counter_v344/openlvds_shunted_counter_v344.drc.txt',
        'openlvds_shunted_counter_v344/openlvds_shunted_counter_v344.drc_count.txt',
        'openlvds_shunted_counter_v344/openlvds_shunted_counter_v344.lvs.log')]
    paths += [ROOT/'scripts/build_shunted_counter_v344.py']
    paths+=sorted({Path(v.__file__).resolve() for v in list(sys.modules.values())
        if getattr(v,'__file__',None) and Path(v.__file__).resolve().parent == ROOT/'scripts'})
    paths+=[Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic/sky130A.magicrc',
            ROOT/'scripts/setup_counter_physical_python_v344.sh']
    inputs=dict(selected_inputs)
    material.merge_expected(inputs,{str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in paths})
    external={str(Path(v.__file__).resolve()):sha(Path(v.__file__).resolve()) for n,v in sys.modules.items()
              if n.startswith(('klayout','numpy','scipy')) and getattr(v,'__file__',None)}
    external[str(Path(sys.executable).resolve())]=sha(Path(sys.executable).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),failed_predecessor=str(FAILED.relative_to(ROOT)),cells=cells,macros=macros,plan=plan,
        reference_sha256=hashlib.sha256(expected.encode()).hexdigest(),inputs=inputs,external_files=external,
        upstream_waveform_hashes={n:h for n,h in i['inputs'].items() if n.endswith('.raw')},
        tools=assembly.native.environment.tools(),python_packages={n:version(n) for n in ('numpy','scipy','klayout')},
        native_contact_checks=checks,native_master_witness=witness,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION or i['scope'] != SCOPE
            or out.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n,h in i['inputs'].items())
            or any(sha(Path(n)) != h for n,h in i['external_files'].items())
            or {n:version(n) for n in i['python_packages']} != i['python_packages']
            or assembly.native.environment.tools() != i['tools']):
        raise ValueError('Captured shunted counter physical context changed')
    old=json.loads((material.PLAN/'manifest.json').read_text())['identity']
    if route_plan(old,i['cells'],i['macros']) != i['plan']:
        raise ValueError('Shunted counter routes cannot regenerate')
    return m


def draw(out, i):
    cells=i['cells'];macros=i['macros'];p=i['plan'];configuration=p['configuration']
    for name,m in macros.items():
        folder=ROOT/m['folder']
        commands=['gds readonly false',f'gds read {{{folder/(name+".gds")}}}']
        for child in sorted(assembly.hierarchy(folder,name)):
            commands += [f'load {child} -silent',f'save {child}']
        layout.invoke_magic(out,'\n'.join(commands),'import_'+name)
    g=layout.Geometry();lookup={c['name']:c for c in cells};public={}
    def via34(x,y,power=False):
        if power:g.via34(x,y)
        else:
            g.pad('metal3',x,y,.4);g.pad('via3',x,y,.32);g.pad('metal4',x,y,.4)
    def via45(x,y):g.pad('via4',x,y,1.8)
    # Draw exactly the contact-checked M4/M5 rectangles, including local shunt
    # and direct feedback. Add only the required M3 stems and via cuts below.
    for row in p['all_m4_m5_shapes']:
        g.rect(row['layer'],*row['rect'])
    for net,ends in p['points'].items():
        power=net in ('VGND','VPWR');by=p['buses'][net]
        for end in ends:
            c=lookup[end['cell']];m=macros[c['model']];pin=m['row']['ports'][end['pin']]
            pos=p['placements'][c['name']];px=pos['x']+pin['x_um'];py=pos['y']+pin['y_um']
            connection=p['base_escapes']['spine_connections'].get(c['name']+'.'+end['pin'])
            cy=connection['y_um'] if connection else py
            if pin['layer'] == 'metal3':
                rail=[r for layer,r in m['lef']['pins'][end['pin']] if layer=='met3'
                      and r[0]<=pin['x_um']<=r[2] and r[1]<=pin['y_um']<=r[3]]
                if len(rail)!=1:raise ValueError('Ambiguous actual native M3 landing')
                if not power:px=pos['x']+rail[0][2]-3.-2*list(c['pins']).index(end['pin'])
                via34(px,py,power)
            if connection and connection['via4_cut_um'] is not None:
                via45(px,py);via45(end['x'],cy)
            via34(end['x'],cy,power)
            width=configuration['power_spine_width_um'] if power else configuration['spine_width_um']
            g.wire('metal3',end['x'],cy,end['x'],by,width)
        for x in sorted({e['x'] for e in ends}):
            g.via34(x,by);via45(x,by)
        if net in PORTS:
            public[net]=dict(layer='metal5',x_um=.3,y_um=by,width_um=2. if power else 1.6)
    for wire in p['direct_feedback']:
        for e in wire['ends']:via34(e['x_um'],e['y_um'])
    a=p['cap_ground_contact'];b=p['ground_setter_contact']
    via45(a['x_um'],a['y_um']);via45(b['x_um'],b['y_um'])
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():
        lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    for c in cells:
        pos=p['placements'][c['name']]
        lines += [f'use {c["model"]} {c["name"]}','timestamp 0',
            f'transform 1 0 {round(pos["x"]/layout.GRID)} 0 1 {round(pos["y"]/layout.GRID)}',
            'box '+' '.join(str(round(v/layout.GRID)) for v in macros[c['model']]['bbox'])]
    lines += ['<< labels >>']
    for k,pin in enumerate(PORTS,1):
        a=public[pin];x=round(a['x_um']/layout.GRID);y=round(a['y_um']/layout.GRID)
        lines += [f'rlabel metal5 {x} {y} {x} {y} 0 {pin}',f'port {k} nsew']
    for net,y in p['buses'].items():
        if net in PORTS:continue
        x=round((min(e['x'] for e in p['points'][net])-1.4)/layout.GRID);y=round(y/layout.GRID)
        lines += [f'rlabel metal5 {x} {y} {x} {y} 0 {net}']
    for wire in p['direct_feedback']:
        a=wire['ends'][0];x=round(a['x_um']/layout.GRID);y=round(a['y_um']/layout.GRID)
        lines += [f'rlabel metal4 {x} {y} {x} {y} 0 {wire["net"]}']
    (out/(NAME+'.mag')).write_text('\n'.join(lines+['<< end >>','']))
    reference=material.reference(cells,macros).replace(material.NAME,NAME)
    if hashlib.sha256(reference.encode()).hexdigest()!=i['reference_sha256']:
        raise ValueError('Passed native counter reference changed')
    (out/(NAME+'.sch.spice')).write_text(reference)
    row=layout.qualify(out,NAME)
    ports,actual=material.legacy.inventory.native_leaves(
        material.collapse((out/(NAME+'.lvs.spice')).read_text()),NAME+'_flat')
    _,expected=material.legacy.inventory.native_leaves(reference,NAME)
    inventory=material.legacy.inventory.compare_parameters(expected,actual)
    counts=(sum('fet_' in d['model'] for d in actual),sum('cap_mim' in d['model'] for d in actual))
    if set(ports)!=set(PORTS) or counts!=(744,51):
        raise ValueError('Extracted whole-counter native inventory or public ports changed')
    raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    types={pin:('OUTPUT' if pin in ('PREPARE','RESET_N','CLK') else 'INPUT','SIGNAL')
           for pin in PORTS if pin not in ('VPWR','VGND')}
    types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=assembly.access.restrict(raw.read_text(),public,types)
    (out/(NAME+'.lef')).write_text(text)
    masks=native_witness(macros,out/(NAME+'.gds'),cells,p['placements'])
    return dict(row,macro=NAME,ports=public,integration_pins=pins,native_master_witness=masks,native_parameters=inventory,
        native_macro_roles=23,native_mos=744,native_mim=51,
        gds_sha256=sha(out/(NAME+'.gds')),lef_sha256=sha(out/(NAME+'.lef')))


def run(out):
    i=bound(out)['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial shunted counter geometry')
        atomic(out/'state.json',dict(status='routing',qualified_phy=False))
        folder=out/NAME;folder.mkdir()
        try:
            row=draw(folder,i);atomic(folder/'summary.json',row)
            bound(out)
            report=dict(physical=row,counter_physical_passed=row['passed'],
                whole_counter_shared_wire_rc_qualified=False,counter_timing_qualified=False,
                qualified_phy=False,scope=SCOPE)
            report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*')
                             if p.is_file() and p.name not in ('state.json','.execution.lock')}
            atomic(out/'summary.json',report)
            atomic(out/'state.json',dict(status='complete',passed=row['passed'],qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json',dict(status='failed',error=str(error),qualified_phy=False));raise
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'))
    parser.add_argument('artifact',type=Path)
    args=parser.parse_args();out=args.artifact.resolve()
    if args.action in ('prepare','campaign'):
        out=prepare(out);print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
