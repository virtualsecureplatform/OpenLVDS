#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One-factor P80/N32 -> P40/N16 fine driver experiment, native maps retained."""
from copy import deepcopy
import probe_pullup_restored_bank_v360 as parent

TOP = 'openlvds_single_fine_driver_300'
SOURCE = parent.source


def transform(text, observations):
    defs = SOURCE.native.definitions(text)
    ports, body = defs[parent.TOP]
    expected = ['Xfine_isolate', 'pre_out', 'fine_node', 'VGND', 'VPWR', parent.FINE]
    if (len(observations['devices']) != 2126 or len(observations['controls']) != 86
            or len(observations['programming_gates']) != 266
            or sum(w == expected for w in body) != 1
            or defs[parent.FINE] != (['A', 'Y', 'VGND', 'VPWR'], [
                ['Xa', 'A', 'Y', 'VGND', 'VPWR', parent.recovery.PULLUP],
                ['Xb', 'A', 'Y', 'VGND', 'VPWR', parent.recovery.PULLUP]])):
        raise ValueError('Require exact qualified two-driver bank and full observation maps')
    # Keep Xa and its complete extracted subcircuit verbatim; only remove Xb.
    wrapper = SOURCE.definition(text, parent.FINE)
    single = '\n'.join(['.subckt '+parent.FINE+' A Y VGND VPWR',
                        'Xa A Y VGND VPWR '+parent.recovery.PULLUP,
                        '.ends '+parent.FINE, ''])
    result = text.replace(wrapper, single, 1).replace(parent.TOP, TOP)
    if any(SOURCE.definition(result, n) != SOURCE.definition(text, n)
           for n in defs if n not in (parent.TOP, parent.FINE)):
        raise ValueError('Unrelated qualified native definition changed')
    devices = SOURCE.native.mapped_mos(result, TOP,
        {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}, 'XD')
    before = {d['name']: d for d in observations['devices']}
    after = {d['name']: d for d in devices}
    removed = 'XD:Xfine_isolate:Xb:'
    if (len(after) != 2070 or len(devices) != 2070
            or sum(n.startswith(removed) for n in before) != 56
            or after != {n: d for n, d in before.items() if not n.startswith(removed)}):
        raise ValueError('Change must remove exactly one 56-MOS driver and preserve all other terminals')
    for gate in observations['programming_gates']:
        if after[gate['device']]['terminals'][1] != gate['gate_node']:
            raise ValueError('Programming-gate observation changed')
    _, leaves = SOURCE.inventory.native_leaves(SOURCE.collapse(result), TOP)
    if (sum('fet_' in d['model'] for d in leaves) != 2070
            or sum('cap_mim' in d['model'] for d in leaves) != 138):
        raise ValueError('Unexpected reachable native MOS/MIM inventory')
    return result, dict(devices=devices, controls=deepcopy(observations['controls']),
                        programming_gates=deepcopy(observations['programming_gates']))
