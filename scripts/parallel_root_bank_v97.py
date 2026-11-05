# SPDX-License-Identifier: GPL-3.0-only
"""Parallel qualified root TG cells to drive the measured fine-cell RC load.

The four new root instances add eight native MOS devices. Their common
interconnect remains ideal until a fresh bank layout/extraction is qualified.
"""
from collections import Counter
from copy import deepcopy
import re
import moscap_component_rc_bank_v90 as base
from short_cap_bus_bank_v94 import checked_cell

ROOT = base.ROOT
source = base.source
WIDTHS = base.WIDTHS
TG = 'openlvds_tg_quad_stacked_nlvt_v27'


def name(profile):
    base.name(profile)
    return 'openlvds_parallel_root_moscap_'+profile+'_v97'


def rename(text, before, after):
    return re.sub(r'\b'+re.escape(before)+r'(?=_unit\b|\b)', after, text)


def root_calls(bank, top):
    defs = source.native.definitions(bank)
    calls = {w[0]: w for w in defs[top][1] if w[0].startswith('X')}
    selected = []
    for k in range(4):
        w = calls.get(f'Xswitch1_0_{k}')
        if w is None or w[-1] != TG or dict(zip(defs[TG][0], w[1:-1])) != dict(
                A=f'regenerated{k}', Z='selected', EN=f'en1_{k}', ENB=f'en_b1_{k}', VPWR='VPWR', VGND='VGND'):
            raise ValueError('Original root mux data/control/body wiring changed')
        selected.append(w)
    return selected


def parallel_roots(bank, top, target):
    roots = root_calls(bank, top)
    if re.search(r'(?m)^Xroot_parallel\d+\b', bank):
        raise ValueError('Root mux already has additional parallel instances')
    before = base.cell_definition(bank, top)
    added = '\n'.join(' '.join([f'Xroot_parallel{k}', *w[1:]]) for k, w in enumerate(roots))+'\n'
    after, count = re.subn(r'(?im)^\.ends\b', added+'.ends', before)
    if count != 1:
        raise ValueError('Ambiguous root-bank boundary')
    return rename(bank.replace(before, after, 1), top, target)


def projection(bank, profile):
    top = name(profile); roots = root_calls(bank, top)
    defs = source.native.definitions(bank); body = defs[top][1]
    parallel = [w for w in body if w[0].startswith('Xroot_parallel')]
    expected = [[f'Xroot_parallel{k}', *w[1:]] for k, w in enumerate(roots)]
    if parallel != expected:
        raise ValueError('Parallel root mux is missing, duplicated or rewired')
    result, count = re.subn(r'(?m)^Xroot_parallel[0-3][ \t][^\n]*\n', '', bank)
    if count != 4:
        raise ValueError('Parallel root mux source layout changed')
    return rename(result, top, base.name(profile))


def transform(text, profile, fine_rc):
    original = base.transform(text, profile, fine_rc)
    bank = parallel_roots(original, base.name(profile), name(profile))
    if projection(bank, profile) != original:
        raise ValueError('Parallel root prototype changes the original bank')
    counts = source.primitive_counts(bank, name(profile))
    if sum(v for k, v in counts.items() if 'fet_' in k) != 1021 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 37:
        raise ValueError('Parallel root native inventory changed')
    return bank


def observations(bank, profile, previous):
    original = projection(bank, profile); result = base.observations(original, profile, previous)
    top = name(profile); ports = source.native.definitions(bank)[top][0]
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(bank, top, mapping, 'XD'); byname = {d['name']: d for d in devices}
    gates = deepcopy(result['programming_gates']); extras = []
    for k in range(4):
        prefix = f'XD:Xswitch1_0_{k}:'; duplicate = f'XD:Xroot_parallel{k}:'
        originals = [g for g in gates if g['device'].startswith(prefix)]
        if len(originals) != 2 or any(g['kind'] != 'tg' for g in originals):
            raise ValueError('Root programming-gate identity changed')
        for g in originals:
            device = duplicate+g['device'][len(prefix):]
            extras.append(dict(g, device=device, gate_node=byname[device]['terminals'][1]))
    gates += extras
    if (len(devices) != 1021 or len(byname) != 1021 or len(gates) != 141
        or Counter(g['kind'] for g in gates) != Counter(fine=93, tg=48)):
        raise ValueError('Incomplete parallel-root native/gate coverage')
    return dict(result, devices=devices, programming_gates=gates)
