# SPDX-License-Identifier: GPL-3.0-only
"""Balance first-mux and group-inverter drive after root/final strengthening.

Duplicate complete qualified cells; retain the existing number of serial
logic stages. Common gang wiring still requires actual bank extraction.
"""
from collections import Counter
from copy import deepcopy
import re
import parallel_final_bank_v100 as base
from parallel_root_bank_v97 import rename
from build_compound_drivers_v3 import cell_definition

ROOT = base.ROOT
source = base.source
WIDTHS = base.WIDTHS
TG = base.base.TG
INV = base.INV


def name(profile):
    base.name(profile)
    return 'openlvds_balanced_drive_'+profile+'_v103'


def upstream_calls(bank, top):
    defs = source.native.definitions(bank)
    calls = {w[0]: w for w in defs[top][1] if w[0].startswith('X')}
    selected = []
    for g in range(4):
        for leaf in range(4):
            w = calls.get(f'Xswitch0_{g}_{leaf}'); k = g*4+leaf
            if (w is None or w[-1] != TG or dict(zip(defs[TG][0], w[1:-1])) != dict(
                A='IN' if k == 0 else f'tap{k}', Z=f'tree0_{g}', EN=f'en0_{leaf}',
                ENB=f'en_b0_{leaf}', VPWR='VPWR', VGND='VGND')):
                raise ValueError('First mux data/control/body wiring changed')
            selected.append((f'Xleaf_parallel{g}_{leaf}', w))
    for g in range(4):
        w = calls.get(f'Xgroup_inverse{g}')
        if (w is None or w[-1] != INV or dict(zip(defs[INV][0], w[1:-1])) != dict(
                A=f'tree0_{g}', Y=f'regenerated{g}', VGND='VGND', VPWR='VPWR')):
            raise ValueError('Group inverter data/body wiring changed')
        selected.append((f'Xgroup_parallel{g}', w))
    return selected


def parallel_upstream(bank, top, target):
    selected = upstream_calls(bank, top)
    if re.search(r'(?m)^X(?:leaf|group)_parallel', bank):
        raise ValueError('Upstream stages are already paralleled')
    before = cell_definition(bank, top)
    added = '\n'.join(' '.join([tag, *w[1:]]) for tag, w in selected)+'\n'
    after, count = re.subn(r'(?im)^\.ends\b', added+'.ends', before)
    if count != 1:
        raise ValueError('Ambiguous balanced bank boundary')
    return rename(bank.replace(before, after, 1), top, target)


def projection(bank, profile):
    top = name(profile); selected = upstream_calls(bank, top)
    parallel = [w for w in source.native.definitions(bank)[top][1]
                if w[0].startswith(('Xleaf_parallel', 'Xgroup_parallel'))]
    if parallel != [[tag, *w[1:]] for tag, w in selected]:
        raise ValueError('Balanced upstream calls missing, duplicated or rewired')
    result, count = re.subn(r'(?m)^X(?:leaf_parallel[0-3]_[0-3]|group_parallel[0-3])[ \t][^\n]*\n', '', bank)
    if count != 20:
        raise ValueError('Balanced upstream source layout changed')
    return rename(result, top, base.name(profile))


def transform(text, profile, fine_rc):
    original = base.transform(text, profile, fine_rc)
    bank = parallel_upstream(original, base.name(profile), name(profile))
    if projection(bank, profile) != original:
        raise ValueError('Balanced driver changes the original bank')
    counts = source.primitive_counts(bank, name(profile))
    if sum(v for k, v in counts.items() if 'fet_' in k) != 1133 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 42:
        raise ValueError('Balanced native inventory changed')
    return bank


def observations(bank, profile, previous):
    result = base.observations(projection(bank, profile), profile, previous)
    ports = source.native.definitions(bank)[name(profile)][0]
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(bank, name(profile), mapping, 'XD'); byname = {d['name']: d for d in devices}
    gates = deepcopy(result['programming_gates']); extras = []
    for g in range(4):
        for leaf in range(4):
            old = f'XD:Xswitch0_{g}_{leaf}:'; new = f'XD:Xleaf_parallel{g}_{leaf}:'
            originals = [r for r in gates if r['device'].startswith(old)]
            if len(originals) != 2 or any(r['kind'] != 'tg' for r in originals):
                raise ValueError('First-mux programming-gate identity changed')
            for r in originals:
                device = new+r['device'][len(old):]
                extras.append(dict(r, device=device, gate_node=byname[device]['terminals'][1]))
    gates += extras
    if (len(devices) != 1133 or len(byname) != 1133 or len(gates) != 173
        or Counter(g['kind'] for g in gates) != Counter(fine=93, tg=80)):
        raise ValueError('Incomplete balanced native/programming coverage')
    return dict(result, devices=devices, programming_gates=gates)
