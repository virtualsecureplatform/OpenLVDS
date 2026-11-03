# SPDX-License-Identifier: GPL-3.0-only
"""Resolve delivered PFD clocks to actual GDS/extracted MOS gate terminals.

Do not substitute a pad, a guessed .tN node or a zero-ohm alias for the
receiving gate. All split input-gate nodes remain separate observations.
"""
from decimal import Decimal
from fractions import Fraction
import re

import slew_pfd_floorplan as floorplan


def equivalents(ext):
    parents = {}
    def root(name):
        parents.setdefault(name, name)
        if parents[name] != name: parents[name] = root(parents[name])
        return parents[name]
    for line in ext.splitlines():
        match = re.fullmatch(r'equiv "([^"]+)" "([^"]+)"', line)
        if match: parents[root(match[2])] = root(match[1])
        elif line.startswith(('node ', 'port ')):
            match = re.match(r'\w+ "([^"]+)"', line)
            if match: root(match[1])
    return parents, root


def coordinate_scale(definition, ext):
    """Derive exact coordinate conversion from both actual public pin boxes."""
    pins = floorplan.pin_records(definition); scales = []
    for name in ('REF', 'FB'):
        if name not in pins: raise ValueError('Missing physical clock pin: ' + name)
        x, y, orientation = floorplan.location(pins[name])
        if orientation != 'N': raise ValueError('Require the retained unrotated input-pin template')
        shapes = re.findall(r'\+ LAYER\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)', pins[name])
        ports = re.findall(r'(?m)^port "' + name + r'" \d+ (-?\d+) (-?\d+) (-?\d+) (-?\d+) (\S+)\s*$', ext)
        if len(shapes) != 1 or len(ports) != 1: raise ValueError('Require one actual rectangular clock-pin shape')
        layer, *rectangle = shapes[0]; box = tuple(map(int, rectangle)); ex0, ey0, ex1, ey1 = map(int, ports[0][:4])
        expected_layer = {'met1': 'm1', 'met2': 'm2', 'met3': 'm3', 'met4': 'm4', 'met5': 'm5'}.get(layer)
        if expected_layer is None or ports[0][4] != expected_layer or ex1 <= ex0 or ey1 <= ey0:
            raise ValueError('Clock-pin layer or extracted geometry differs')
        scale = Fraction(box[2] - box[0], ex1 - ex0)
        expected = (x + box[0], y + box[1], x + box[2], y + box[3])
        if scale <= 0 or tuple(scale * v for v in (ex0, ey0, ex1, ey1)) != expected:
            raise ValueError('Extracted and physical clock-pin coordinates disagree')
        scales.append(scale)
    if scales[0] != scales[1]: raise ValueError('Clock pins imply different extraction scales')
    return scales[0]


def cell_box(definition, lef, instance):
    matches = re.findall(r'(?ms)^\s*-\s+' + re.escape(instance) + r'\s+(\S+)(.*?);', floorplan.section(definition, 'COMPONENTS'))
    if len(matches) != 1 or matches[0][0] != 'sky130_fd_sc_hd__dfrtp_4': raise ValueError('Require one preserved dfrtp_4 receiver: ' + instance)
    master, entry = matches[0]; x, y, orientation = floorplan.location(entry)
    if orientation not in ('N', 'S', 'FN', 'FS'): raise ValueError('Unsupported standard-cell orientation')
    macros = re.findall(r'(?ms)^MACRO\s+' + master + r'\s+(.*?)^END\s+' + master + r'\s*$', lef)
    if len(macros) != 1: raise ValueError('Missing or duplicate actual FF LEF')
    sizes = re.findall(r'\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;', macros[0])
    origins = re.findall(r'\bORIGIN\s+(-?[\d.]+)\s+(-?[\d.]+)\s*;', macros[0])
    if len(sizes) != 1 or any(Decimal(v) != 0 for origin in origins for v in origin): raise ValueError('Unsupported FF LEF origin or size')
    dbu = floorplan.units(definition); width, height = (Decimal(v) * dbu for v in sizes[0])
    if width <= 0 or height <= 0 or width != int(width) or height != int(height): raise ValueError('FF geometry is off the DEF grid')
    return dict(master=master, orientation=orientation, box_dbu=[x, y, x + int(width), y + int(height)])


def devices(ext):
    result = {}
    for line in ext.splitlines():
        match = re.match(r'^device msubckt (\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) (.*)$', line)
        if not match: continue
        model = match[1]
        if 'nfet' not in model and 'pfet' not in model: continue
        key = (model, *map(int, match.groups()[1:5])); nodes = re.findall(r'"([^"]+)"', match[6])
        if key in result or len(nodes) != 4: raise ValueError('Ambiguous extracted MOS geometry or terminal order')
        result[key] = dict(model=model, geometry_grid=list(key[1:]), bulk=nodes[0], gate=nodes[1], diffusion_nodes=nodes[2:])
    if not result: raise ValueError('No extracted MOS devices')
    return result


def derive(definition, lef, ext, resistive_ext, native):
    scale = coordinate_scale(definition, ext); before = devices(ext); after = devices(resistive_ext)
    parents, root = equivalents(ext)
    gates = set()
    for line in native.splitlines():
        words = line.split()
        if not words or not words[0].lower().startswith('x'): continue
        stop = next((i for i, word in enumerate(words) if '=' in word), len(words))
        if stop >= 6 and ('nfet' in words[stop-1] or 'pfet' in words[stop-1]): gates.add(words[2])
    observations = {}
    for label, instance in [('REF_FF_CLK', 'ref_ff'), ('FB_FF_CLK', 'fb_ff')]:
        pin = instance + '.CLK'; geometry = cell_box(definition, lef, instance); box = geometry['box_dbu']
        if pin not in parents: raise ValueError('GDS lacks the FF clock-pin equivalence: ' + pin)
        selected = []
        for key, device in before.items():
            if root(device['gate']) != root(pin): continue
            xy = [scale * v for v in device['geometry_grid']]
            if any(v.denominator != 1 for v in xy): raise ValueError('MOS coordinate is off the physical database grid')
            x0, y0, x1, y1 = map(int, xy)
            if not (box[0] <= x0 < x1 <= box[2] and box[1] <= y0 < y1 <= box[3]):
                raise ValueError('Clock net reaches a MOS gate outside its receiving FF')
            if key not in after or after[key]['gate'] not in gates: raise ValueError('Actual receiving MOS gate is absent from native RC')
            selected.append(dict(model=device['model'], geometry_grid=device['geometry_grid'],
                                 geometry_dbu=[x0, y0, x1, y1], native_node=after[key]['gate']))
        if not selected or not all(any(kind in d['model'] for d in selected) for kind in ('nfet', 'pfet')):
            raise ValueError('Receiving FF clock lacks its complete CMOS input pair')
        selected.sort(key=lambda d: (d['model'], d['geometry_grid']))
        observations[label] = dict(physical_pin=pin, cell=geometry, mos_gates=selected,
                                   native_nodes=sorted({d['native_node'] for d in selected}))
    if set(observations['REF_FF_CLK']['native_nodes']) & set(observations['FB_FF_CLK']['native_nodes']):
        raise ValueError('Independent PFD clock inputs share a native gate node')
    return dict(coordinate_scale_dbu_per_grid=[scale.numerator, scale.denominator], observations=observations,
                scope='Actual receiving MOS gate nodes, mapped by GDS geometry before/after extresist; every split gate observed separately. No ideal aliases or pad substitution.',
                route_matching_verified=False, physical_admission=False, qualified_phy=False)


def probes(observations, prefix):
    if not prefix or not prefix.endswith(':'): raise ValueError('Require an explicit instantiated PFD hierarchy prefix')
    return {name + '_' + str(i): prefix + node for name, group in observations['observations'].items()
            for i, node in enumerate(group['native_nodes'])}
