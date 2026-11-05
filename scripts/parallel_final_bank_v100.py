# SPDX-License-Identifier: GPL-3.0-only
"""Parallel the existing final inverter after the strengthened root mux.

Both complete native cell models and their output shunts are retained.
The new common input/output wiring is unqualified until bank extraction.
"""
import re
import parallel_root_bank_v97 as base

ROOT = base.ROOT
source = base.source
WIDTHS = base.WIDTHS
checked_cell = base.checked_cell
INV = 'openlvds_inv_8_nlvt_o2_v34'


def name(profile):
    base.name(profile)
    return 'openlvds_parallel_final_moscap_'+profile+'_v100'


def driver_call(bank, top):
    defs = source.native.definitions(bank)
    calls = [w for w in defs[top][1] if w[0] == 'Xfine_driver']
    if len(calls) != 1 or calls[0][-1] != INV or dict(zip(defs[INV][0], calls[0][1:-1])) != dict(
            A='selected', Y='OUT', VGND='VGND', VPWR='VPWR'):
        raise ValueError('Original final inverter data/body wiring changed')
    return calls[0]


def parallel_driver(bank, top, target):
    driver = driver_call(bank, top)
    if re.search(r'(?m)^Xfine_parallel\b', bank):
        raise ValueError('Final inverter is already paralleled')
    before = base.base.cell_definition(bank, top)
    added = ' '.join(['Xfine_parallel', *driver[1:]])+'\n'
    after, count = re.subn(r'(?im)^\.ends\b', added+'.ends', before)
    if count != 1:
        raise ValueError('Ambiguous final-stage bank boundary')
    return base.rename(bank.replace(before, after, 1), top, target)


def projection(bank, profile):
    top = name(profile); driver = driver_call(bank, top)
    parallel = [w for w in source.native.definitions(bank)[top][1] if w[0] == 'Xfine_parallel']
    if parallel != [['Xfine_parallel', *driver[1:]]]:
        raise ValueError('Parallel final inverter is missing, duplicated or rewired')
    result, count = re.subn(r'(?m)^Xfine_parallel[ \t][^\n]*\n', '', bank)
    if count != 1:
        raise ValueError('Parallel final inverter source layout changed')
    return base.rename(result, top, base.name(profile))


def transform(text, profile, fine_rc):
    original = base.transform(text, profile, fine_rc)
    bank = parallel_driver(original, base.name(profile), name(profile))
    if projection(bank, profile) != original:
        raise ValueError('Final parallel prototype changes the original root bank')
    counts = source.primitive_counts(bank, name(profile))
    if sum(v for k, v in counts.items() if 'fet_' in k) != 1037 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 38:
        raise ValueError('Parallel final native inventory changed')
    return bank


def observations(bank, profile, previous):
    original = projection(bank, profile); result = base.observations(original, profile, previous)
    ports = source.native.definitions(bank)[name(profile)][0]
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(bank, name(profile), mapping, 'XD')
    if (len(devices) != 1037 or len({d['name'] for d in devices}) != 1037
        or sum(d['name'].startswith('XD:Xfine_parallel:') for d in devices) != 16
        or len(result['programming_gates']) != 141):
        raise ValueError('Incomplete parallel-final native/gate coverage')
    return dict(result, devices=devices)
