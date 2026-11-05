# SPDX-License-Identifier: GPL-3.0-only
"""Restore only lost tied-terminal junctions from measured isolated primitives.

Callers must prove that the placed primitive diffusion/poly/well masks equal
the measured primitives and that their active regions remain separate.
"""
from collections import Counter
from copy import deepcopy
import re
import layout
import native_bank_inventory_v51 as inventory
from audit_rc_comments_v2 import collapse

FIELDS = ('ad', 'as', 'pd', 'ps')


def geometry_key(d):
    return d['model'], inventory.exact_number(d['params']['w']), inventory.exact_number(d['params']['l'])


def junction_library(rows):
    library = {}
    for row in rows:
        p = row['primitive']; actual = row['actual']
        key = (p['model'], inventory.exact_number(p['width_um']), inventory.exact_number(p['length_um']))
        if (key in library or geometry_key(actual) != key or len(actual['nodes']) != 4
            or actual['nodes'][1] != 'G' or actual['nodes'][3] != 'B'
            or set((actual['nodes'][0], actual['nodes'][2])) != {'D', 'S'}
            or not row['geometry']['passed'] or row['geometry']['drc_count'] != '0'):
            raise ValueError('Invalid isolated primitive terminal/geometry measurement')
        values = {f: actual['params'][f] for f in FIELDS}
        if any(inventory.exact_number(v) <= 0 for v in values.values()):
            raise ValueError('Isolated junction measurement is not positive')
        if actual['nodes'][0] == 'S':
            values = dict(ad=values['as'], **{'as': values['ad']}, pd=values['ps'], ps=values['pd'])
        library[key] = dict(values=values, cell=p['cell'])
    return library


def normalize(devices, ports):
    private = {n for d in devices for n in d['nodes'] if n not in ports}
    if len(private) != 1:
        raise ValueError('Require exactly one switched-capacitor internal net')
    cap = next(iter(private))
    return [dict(d, nodes=['__CAP' if n == cap else n for n in d['nodes']]) for d in devices]


def topology_key(d):
    n = d['nodes']
    if 'fet_' in d['model']:
        return (*geometry_key(d), n[1], n[3], tuple(sorted((n[0], n[2]))))
    return (*geometry_key(d), tuple(sorted(n)))


def reconstruct(raw, top, reference, rows):
    """Return a corrected raw netlist and full reference, preserving every R/C.

    Only zero area/perimeter on the two D=S=body capacitor MOS devices may
    change. Ambiguous D/S orientation requires symmetric measured junctions.
    """
    ports, expected = inventory.native_leaves(reference, top)
    rc_ports, actual = inventory.native_leaves(collapse(raw), top)
    if ports != rc_ports or ports != ['NODE', 'EN', 'ENB', 'VDD', 'VSS']:
        raise ValueError('Fine-cell interface changed')
    e = normalize(expected, ports); a = normalize(actual, ports)
    if Counter(map(topology_key, e)) != Counter(map(topology_key, a)) or len(e) != 6:
        raise ValueError('RC native topology/model/dimensions changed')
    library = junction_library(rows)
    if any(geometry_key(d) not in library for d in e if 'fet_' in d['model']):
        raise ValueError('Missing isolated primitive junction measurement')
    mapping = {topology_key(d): d for d in e}
    if len(mapping) != len(e):
        raise ValueError('Ambiguous physical-to-RC primitive identity')
    corrections = []; replacements = {}; full = deepcopy(expected)
    for d in full:
        if 'fet_' in d['model']:
            d['params'].update(library[geometry_key(d)]['values'])
    for d in a:
        if 'fet_' not in d['model']:
            continue
        original = mapping[topology_key(d)]; measured = library[geometry_key(d)]
        target = dict(measured['values']); n = d['nodes']; en = original['nodes']
        tied = n[0] == n[2] == n[3] and n[3] in ('VDD', 'VSS') and n[1] == '__CAP'
        if n[0] == n[2]:
            if any(inventory.exact_number(target[x]) != inventory.exact_number(target[y])
                   for x, y in [('ad', 'as'), ('pd', 'ps')]):
                raise ValueError('Tied D/S orientation has asymmetric measured junctions')
        elif n[0] != en[0]:
            target = dict(ad=target['as'], **{'as': target['ad']}, pd=target['ps'], ps=target['pd'])
        changes = {}
        for field in FIELDS:
            before = d['params'].get(field)
            if before is None:
                raise ValueError('RC MOS omits a junction parameter')
            if inventory.exact_number(before) != inventory.exact_number(target[field]):
                if not tied or inventory.exact_number(before) != 0:
                    raise ValueError('Unexpected nonzero or non-capacitor junction mismatch')
                changes[field] = target[field]
        if changes:
            instance = d['name'].removeprefix('native__')
            replacements[instance] = changes
            corrections.append(dict(instance=instance, primitive_cell=measured['cell'],
                                    before={f: d['params'][f] for f in changes}, after=changes))
    if len(corrections) != 2:
        raise ValueError('Require exactly two lost gate-capacitor junctions')
    lines = raw.splitlines(keepends=True); seen = set()
    for index, line in enumerate(lines):
        words = line.split()
        if not words or words[0] not in replacements:
            continue
        instance = words[0]
        if instance in seen:
            raise ValueError('Duplicate raw MOS instance')
        seen.add(instance)
        for field, value in replacements[instance].items():
            line, count = re.subn(r'(?<!\S)'+field+r'=[^\s$]+', field+'='+value, line)
            if count != 1:
                raise ValueError('Unsupported raw MOS parameter/continuation layout')
        lines[index] = line
    if seen != set(replacements):
        raise ValueError('RC MOS names differ from collapsed primitive names')
    corrected = ''.join(lines)
    # A second parameter comparison against the measured reference catches
    # incorrect replacement, D/S exchange and missing/extra native devices.
    _, check = inventory.native_leaves(collapse(corrected), top)
    params = inventory.compare_parameters(full, check)
    full_reference = layout.schematic_text(top+'_flat', ports, full)
    return corrected, full_reference, dict(corrections=corrections, parameters=params,
        passive_lines_preserved=all(before == after for before, after in zip(raw.splitlines(), corrected.splitlines())
                                    if before.lstrip().startswith(('R', 'r', 'C', 'c'))),
        qualified_phy=False)
