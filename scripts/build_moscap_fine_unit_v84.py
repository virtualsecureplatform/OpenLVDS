#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build compact two-row gate-cap fine cells using inspected native PCells.

Standalone component geometry only. No existing registry or bank is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import layout
import moscap_fine_unit_v77 as unit
from inspect_mim_switch_2x3_pcells_v2 import sha, tools

ROOT = layout.ROOT


def draw(out, profile, library):
    top = unit.name(profile)
    ports, devices = layout.flatten(layout.circuits(unit.schematic(profile)), top)
    g = layout.Geometry(); uses = []; connections = {n: [] for n in [*ports, 'CAP']}
    centers = [(2., 2.), (6., 2.), (10., 2.), (4., -2.6), (8., -2.6), (4.5, 3.3)]
    tracks = dict(B=-1.5, D=-.8, G=0., S=.8)
    for i, (d, (cx, cy)) in enumerate(zip(devices, centers)):
        cell, info = library[layout.primitive_key(d)]
        uses.append((cell, f'I{i}', round(cx/layout.GRID), round(cy/layout.GRID),
                     [round(v/layout.GRID) for v in info['bbox']]))
        pins = {n: (layer, x+cx, y+cy) for n, (layer, x, y) in info['ports'].items()}
        if 'fet_' in d['model']:
            for pin, net in zip(['D', 'G', 'S', 'B'], d['nodes']):
                net = net.removeprefix(top+'__')
                # Gate-cap D/S/body share a local M1 rail escape; their gates
                # retain a separate track. This fits the original fine-cell pitch.
                _, px, py = pins[pin]
                track = cx+(-.7 if i in (3, 4) and pin != 'G' else tracks[pin])
                if pin == 'B':
                    g.pad('locali', px, py, .33); g.pad('viali', px, py, .17)
                    g.pad('metal1', px, py, .4)
                if pin == 'G':
                    g.wire('metal1', px, py, px, py+.3, .18); py += .3
                g.wire('metal1', px, py, track, py, .18); g.via12(track, py)
                connections[net].append((track, py))
        else:
            # Retain the ENB guard, escape its top plate above its entire M3
            # bottom plate, and descend locally outside the capm exclusion.
            _, x, y = pins['C1']
            g.wire('metal4', x, y, x, 7., .6)
            g.wire('metal4', x, 7., 6., 7., .6)
            g.via34(6., 7.); g.via23(6., 7.)
            connections['ENB'].append((6., 7.))
            _, x, y = pins['C2']
            g.wire('metal3', x, y, 6.6, y, .4); g.via23(6.6, y)
            connections['VSS'].append((6.6, y))
    buses = dict(NODE=.3, EN=8.7, ENB=9.5, VDD=10.4, VSS=11.4, CAP=7.9)
    labels = []; public = {}
    for net, points in connections.items():
        y = buses[net]; width = .6 if net in ('VDD', 'VSS') else .4
        left = .3 if net in ports else min(x for x, _ in points)-.2
        right = 12.1 if net in ports else max(x for x, _ in points)+.2
        g.wire('metal3', left, y, right, y, width)
        for x, start in points:
            g.wire('metal2', x, start, x, y, .18); g.via23(x, y)
        labels.append((net, left, y, ports.index(net)+1 if net in ports else None))
        if net in ports:
            public[net] = dict(layer='metal3', x_um=left, y_um=y, width_um=width)
    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rects in g.layers.items():
        lines.append(f'<< {layer} >>')
        lines.extend('rect '+' '.join(map(str, r)) for r in rects)
    for cell, instance, x, y, bb in uses:
        lines += [f'use {cell} {instance}', 'timestamp 0', f'transform 1 0 {x} 0 1 {y}',
                  'box '+' '.join(map(str, bb))]
    lines.append('<< labels >>')
    for net, x, y, port in labels:
        x = round(x/layout.GRID); y = round(y/layout.GRID)
        label = net if port else top+'__'+net
        lines.append(f'rlabel metal3 {x} {y} {x} {y} 0 {label}')
        if port:
            lines.append(f'port {port} nsew')
    lines.append('<< end >>')
    (out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(top+'.sch.spice')).write_text(layout.schematic_text(top, ports, devices))
    return dict(ports=public, devices=len(devices))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--profile', choices=list(unit.WIDTHS), required=True)
    a = p.parse_args(); parent = a.parent.resolve()
    if not parent.is_relative_to(ROOT/'build/diagnostics/moscap_fine_pcells_v77'):
        raise ValueError('Require native gate-cap PCell inspection')
    manifest = json.loads((parent/'manifest.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n) != v for n, v in manifest['code'].items())
        or any(sha(Path(n)) != v for n, v in manifest['pdk_files'].items())
        or tools() != manifest['tools']):
        raise ValueError('Primitive inspection inputs changed')
    report = json.loads((parent/'summary.json').read_text())
    for d in report['library']:
        if sha(parent/(d['cell']+'.mag')) != d['sha256']:
            raise ValueError('Primitive geometry changed')
        if layout.pcell_info(parent/(d['cell']+'.mag')) != d['geometry']:
            # JSON serializes port tuples as lists.
            if json.loads(json.dumps(layout.pcell_info(parent/(d['cell']+'.mag')))) != d['geometry']:
                raise ValueError('Primitive pin geometry changed')
    identity = dict(version='moscap-fine-compact-two-row-native-layout-v84.1', profile=a.profile,
                    code={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), Path(unit.__file__),
                          Path(layout.__file__), ROOT/'scripts/lvs_utils.py',
                          ROOT/'scripts/inspect_mim_switch_2x3_pcells_v2.py']},
                    parent_files={str((parent/n).relative_to(ROOT)): sha(parent/n)
                                  for n in ('manifest.json', 'summary.json')}, tools=tools())
    out = ROOT/'build/diagnostics/moscap_fine_physical_v84'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(out, flush=True)
    for d in report['library']:
        shutil.copy2(parent/(d['cell']+'.mag'), out/(d['cell']+'.mag'))
    library = {(d['model'], d['width_um'], d['length_um']): (d['cell'], d['geometry'])
               for d in report['library']}
    result = draw(out, a.profile, library)
    result.update(layout.qualify(out, unit.name(a.profile)))
    result.update(qualified_phy=False, electrical_qualification_passed=False,
                  scope='Isolated native fine-cell geometry DRC/LVS; no RC or bank timing admission')
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
