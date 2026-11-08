#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Single qualified P40 pre-driver control for the split-one-cell fine bank."""
from copy import deepcopy
import distributed_fine_bank_300 as parent

SOURCE = parent.SOURCE
TOP = 'openlvds_medium_pre_split_c1_300'
PRE = 'openlvds_single_p40_pre_300'


def transform(original, observations):
    text, previous, revision = parent.transform(original, observations, 'split_c1_c1')
    definitions = SOURCE.native.definitions(text)
    old_top = revision['macro_top']
    ports, body = definitions[old_top]
    fine = parent.mim.single.parent.FINE
    leaf = parent.mim.single.parent.recovery.PULLUP
    expected = ['Xfine_pre', 'selected', 'pre_out', 'VGND', 'VPWR', fine]
    if (body.count(expected) != 1 or PRE in definitions or TOP in definitions
            or definitions[fine] != (['A', 'Y', 'VGND', 'VPWR'], [
                ['Xa', 'A', 'Y', 'VGND', 'VPWR', leaf],
                ['Xb', 'A', 'Y', 'VGND', 'VPWR', leaf]])):
        raise ValueError('Require exact two-parallel qualified pre-driver')
    changed = [w[:-1] + [PRE] if w == expected else w for w in body]
    top = '\n'.join(['.subckt ' + TOP + ' ' + ' '.join(ports),
                     *[' '.join(w) for w in changed], '.ends ' + TOP, ''])
    wrapper = '\n'.join(['.subckt ' + PRE + ' A Y VGND VPWR',
                         'Xa A Y VGND VPWR ' + leaf, '.ends ' + PRE, ''])
    result = text.replace(SOURCE.definition(text, old_top), top, 1) + '\n' + wrapper
    if any(SOURCE.definition(result, n) != SOURCE.definition(text, n)
           for n in definitions if n != old_top):
        raise ValueError('Unrelated extracted cell changed')
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = SOURCE.native.mapped_mos(result, TOP, pins, 'XD')
    before = {d['name']: d for d in previous['devices']}
    after = {d['name']: d for d in devices}
    removed = 'XD:Xfine_pre:Xb:'
    if (len(after) != len(devices) or sum(n.startswith(removed) for n in before) != 56
            or after != {n: d for n, d in before.items() if not n.startswith(removed)}):
        raise ValueError('Must remove only the second 56-MOS pre-driver branch')
    for gate in previous['programming_gates']:
        if after[gate['device']]['terminals'][1] != gate['gate_node']:
            raise ValueError('Programming-gate coverage changed')
    _, leaves = SOURCE.inventory.native_leaves(SOURCE.collapse(result), TOP)
    mos = sum('fet_' in d['model'] for d in leaves)
    mims = sum('cap_mim' in d['model'] for d in leaves)
    if (mos, mims) != (revision['native_mos'] - 56, revision['native_mims'] - 1):
        raise ValueError('Reachable native inventory changed unexpectedly')
    return result, dict(devices=devices, controls=deepcopy(previous['controls']),
        programming_gates=deepcopy(previous['programming_gates'])), dict(
        macro_top=TOP, native_mos=mos, native_mims=mims,
        pre_driver='single_qualified_p40n16', fine_driver=revision['fine_driver'],
        fine_copies_pre_node=1, fine_copies_fine_node=1,
        controls=len(previous['controls']), programming_gates=len(previous['programming_gates']),
        shared_wire_rc_qualified=False, qualified_phy=False,
        scope='Untested single-factor architecture control; no timing or electrical admission')
