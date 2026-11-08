#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""P40/N32 pre-driver control assembled from two retained P20/N16 cells."""
from copy import deepcopy
import medium_pre_distributed_bank_300 as parent

SOURCE = parent.SOURCE
TOP = 'openlvds_p40n32_pre_split_c1_300'


def transform(original, observations):
    text, previous, revision = parent.transform(original, observations)
    definitions = SOURCE.native.definitions(text)
    ports, body = definitions[parent.TOP]
    expected = ['Xfine_pre', 'selected', 'pre_out', 'VGND', 'VPWR', parent.PRE]
    wrapper = SOURCE.FINE
    leaf = SOURCE.REGULAR
    if (body.count(expected) != 1 or TOP in definitions
            or definitions[wrapper] != (['A', 'Y', 'VGND', 'VPWR'], [
                ['Xa', 'A', 'Y', 'VGND', 'VPWR', leaf],
                ['Xb', 'A', 'Y', 'VGND', 'VPWR', leaf]])):
        raise ValueError('Require two verbatim retained P20/N16 cells')
    changed = [w[:-1] + [wrapper] if w == expected else w for w in body]
    top = '\n'.join(['.subckt ' + TOP + ' ' + ' '.join(ports),
                     *[' '.join(w) for w in changed], '.ends ' + TOP, ''])
    result = text.replace(SOURCE.definition(text, parent.TOP), top, 1)
    if any(SOURCE.definition(result, n) != SOURCE.definition(text, n)
           for n in definitions if n != parent.TOP):
        raise ValueError('Unrelated retained native component changed')
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = SOURCE.native.mapped_mos(result, TOP, pins, 'XD')
    before = {d['name']: d for d in previous['devices']}
    after = {d['name']: d for d in devices}
    prefix = 'XD:Xfine_pre:'
    actual = SOURCE.native.mapped_mos(text, wrapper,
        dict(A='XD:selected', Y='XD:pre_out', VGND='0', VPWR='VDD'), 'XD:Xfine_pre')
    retained = {n: d for n, d in before.items() if not n.startswith(prefix)}
    if (len(after) != len(devices) or len(before) - len(retained) != 56
            or len(actual) != 72 or after != {**retained, **{d['name']: d for d in actual}}):
        raise ValueError('Change must replace only the complete pre-driver terminal map')
    for gate in previous['programming_gates']:
        if after[gate['device']]['terminals'][1] != gate['gate_node']:
            raise ValueError('Programming-gate coverage changed')
    _, leaves = SOURCE.inventory.native_leaves(SOURCE.collapse(result), TOP)
    mos = sum('fet_' in d['model'] for d in leaves)
    mims = sum('cap_mim' in d['model'] for d in leaves)
    if (mos, mims) != (revision['native_mos'] + 16, revision['native_mims'] + 1):
        raise ValueError('Unexpected reachable native inventory')
    return result, dict(devices=devices, controls=deepcopy(previous['controls']),
        programming_gates=deepcopy(previous['programming_gates'])), dict(
        macro_top=TOP, native_mos=mos, native_mims=mims,
        pre_driver='two_parallel_qualified_p20n16', fine_driver=revision['fine_driver'],
        fine_copies_pre_node=1, fine_copies_fine_node=1,
        controls=len(previous['controls']), programming_gates=len(previous['programming_gates']),
        shared_wire_rc_qualified=False, qualified_phy=False,
        scope='Untested P40/N32 pre-driver recovery control; no timing or electrical admission')
