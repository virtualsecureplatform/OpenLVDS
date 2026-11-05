#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compact two-native-MOS TG with separate controls and actual component RC."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import inspect_tg_device_pcells_v10 as primitives
import layout
import extract_native_flat_v4 as extraction
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup, clean_match
from spice_library import checked_netlist

ROOT = layout.ROOT
sha = primitives.sha
VERSION = 'native-separated-body-compact-quad-tg-cell-physical-rc-v21.1'
CONTEXT = 'tg_quad_cell_v21'
NAME = 'openlvds_tg_quad_physical_v21'
PORTS = ['A', 'Z', 'EN', 'ENB', 'VPWR', 'VGND']
N = 'sky130_fd_pr__nfet_01v8'
P = 'sky130_fd_pr__pfet_01v8'


def schematic():
    return (f'.subckt {NAME} '+ ' '.join(PORTS)+'\n'
            f'XN A EN Z VGND {N} w=1.68 l=.15 ad=.4872 as=.4872 pd=3.94 ps=3.94\n'
            f'XP Z ENB A VPWR {P} w=3.36 l=.15 ad=.9744 as=.9744 pd=7.3 ps=7.3\n'
            f'.ends {NAME}\n')


def native_check(text):
    defs = layout.circuits(text)
    if len(defs) != 1:
        raise ValueError('Require one flat native TG extraction')
    ports, devices = next(iter(defs.values()))
    if set(ports) != set(PORTS) or len(devices) != 2:
        raise ValueError('Native TG lost a public port or transistor')
    seen = set()
    for _, nodes, model, params in devices:
        if model in seen or model not in (N, P):
            raise ValueError('Native TG device model changed')
        seen.add(model)
        gate, body, ends, w, area, perimeter = ('EN', 'VGND', {'A', 'Z'}, 1.68, .4872, 3.94) if model == N else ('ENB', 'VPWR', {'A', 'Z'}, 3.36, .9744, 7.3)
        expected = dict(w=w, l=.15, ad=area, **{'as': area}, pd=perimeter, ps=perimeter)
        if nodes[1] != gate or nodes[3] != body or {nodes[0], nodes[2]} != ends or {k: float(v) for k, v in params.items()} != expected:
            raise ValueError('Native TG terminals, dimensions or junctions changed')
    return dict(two_native_mos_preserved=True, actual_junctions_match_standalone_pcells=True)


def prepare(parent):
    primitives.bound(parent); r = json.loads((parent/'summary.json').read_text())
    if not r['primitive_gds_native_geometry_verified'] or r['qualified_phy']:
        raise ValueError('Require fresh-GDS primitive geometry inspection')
    if any(sha(parent/n) != h for n, h in r['files'].items()):
        raise ValueError('Native primitive outputs changed')
    selected = [c for c in r['cells'] if (c['recipe']['model'], c['recipe']['w']) in ((N, 1.68), (P, 3.36))]
    if len(selected) != 2 or any(set(c['geometry']['ports']) != {'D', 'G', 'S', 'B'} for c in selected):
        raise ValueError('Require both exact native TG PCell interfaces')
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    paths = [parent/'manifest.json', parent/'summary.json']+[parent/(c['recipe']['cell']+'.mag') for c in selected]
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), cells=selected,
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code}, tools=primitives.environment.tools())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(schematic())
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in {**i['inputs'], **i['code']}.items())
            or primitives.environment.tools() != i['tools'] or (out/(NAME+'.sch.spice')).read_text() != schematic()):
        raise ValueError('Native compact TG context changed')
    primitives.bound(ROOT/i['parent'])
    return i


def draw(out, i):
    g = layout.Geometry(); uses = []; interfaces = {}
    for c in i['cells']:
        x = 0. if c['recipe']['model'] == N else 4.
        cell = c['recipe']['cell']; info = c['geometry']
        shutil.copy2(ROOT/i['parent']/(cell+'.mag'), out/(cell+'.mag'))
        interfaces[c['recipe']['model']] = {p: (x+v[1], v[2]) for p, v in info['ports'].items()}
        uses.append((cell, 'nmos' if x == 0 else 'pmos', x, info['bbox']))
    # D/S escape in narrow M1 before adding the wider via landing.
    drops = dict(A=[], Z=[], EN=[], ENB=[], VPWR=[], VGND=[])
    for model, dnet, snet, control, body, left, right in ((N, 'A', 'Z', 'EN', 'VGND', -1.2, 1.2),
                                                      (P, 'Z', 'A', 'ENB', 'VPWR', 2.8, 5.2)):
        pins = interfaces[model]
        for pin, net, column in (('D', dnet, left), ('S', snet, right)):
            x, y = pins[pin]; g.wire('metal1', x, y, column, y, .18); g.via12(column, y); drops[net].append((column, y))
        # A 0.5 um rise clears the native gate-pad notch; 0.3 um fails met1.2.
        x, y = pins['G']; column = left if model == N else right
        g.wire('metal1', x, y, x, y+.5, .18); g.wire('metal1', x, y+.5, column, y+.5, .18)
        g.via12(column, y+.5); drops[control].append((column, y+.5))
        x, y = pins['B']; g.pad('locali', x, y, .33); g.pad('viali', x, y, .17); g.pad('metal1', x, y, .4)
        g.via12(x, y); drops[body].append((x, y))
    ys = dict(A=-3.4, Z=-2.6, EN=3.4, ENB=4.2, VPWR=-5., VGND=-4.2)
    ports = {}
    for pin in PORTS:
        y = ys[pin]; points = drops[pin]
        for x, py in points:
            g.wire('metal2', x, py, x, y, .4); g.via23(x, y)
        left = min(x for x, _ in points)-.4; right = max(x for x, _ in points)+.4
        g.wire('metal3', left, y, right, y, .4)
        ports[pin] = dict(layer='metal3', x_um=left, y_um=y, width_um=.4)
    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rectangles in g.layers.items():
        lines += ['<< '+layer+' >>', *['rect '+' '.join(map(str, rect)) for rect in rectangles]]
    for cell, tag, x, box in uses:
        lines += [f'use {cell} {tag}', 'timestamp 0', f'transform 1 0 {round(x/layout.GRID)} 0 1 0',
                  'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines += ['<< labels >>']
    for index, pin in enumerate(PORTS, 1):
        p = ports[pin]; x, y = round(p['x_um']/layout.GRID), round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}', f'port {index} nsew']
    (out/(NAME+'.mag')).write_text('\n'.join(lines+['<< end >>', '']))
    return ports


def run(out):
    i = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior or partial TG physical evidence')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        ports = draw(out, i)
        physical = layout.qualify(out, NAME)
        (out/'physical.json').write_text(json.dumps(physical, indent=2)+'\n')
        if not physical['passed']:
            raise ValueError('Compact TG physical DRC/LVS failed; retain evidence')
        native = native_check((out/(NAME+'.lvs.spice')).read_text())
        digest = hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():
            raise ValueError('Retain prior TG extraction')
        rc = extraction.extract(NAME, out/(NAME+'.gds'), sha(out/'manifest.json'), ports=ports, source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc, indent=2)+'\n')
        text = checked_netlist(rc)
        if not audit(text)['elementwise_passive_passed']:
            raise ValueError('Compact TG RC failed passivity')
        collapsed = out/'wire_collapsed.spice'; collapsed.write_text(collapse(text))
        setup = strict_setup(out/'rc_setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log = out/'rc_lvs.log'
        p = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {NAME}', f'{out/(NAME+".sch.spice")} {NAME}', str(setup), str(log)], cwd=out, capture_output=True, text=True)
        (out/'rc_console.log').write_text(p.stdout+p.stderr)
        if not clean_match(log.read_text() if log.exists() else '', p.returncode):
            raise ValueError('Compact TG RC topology failed strict LVS')
        bound(out)
        report = dict(physical=physical, ports=ports, native=native, extraction=rc, rc_topology_passed=True,
                      component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                      scope='Two native TG devices, real local signal/control/body routes and fresh passive component RC; no decoder/common/tree wiring or bank timing admission')
        report['files'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock', 'state.json')}
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'campaign']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); out = a.artifact.resolve()
    if a.action in ('prepare', 'campaign'):
        out = prepare(out); print(out, flush=True)
    if a.action in ('run', 'campaign'):
        print(run(out), flush=True)
