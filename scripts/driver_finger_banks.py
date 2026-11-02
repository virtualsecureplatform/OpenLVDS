# SPDX-License-Identifier: GPL-3.0-only
"""Group identical physical fingers for compact PCells without changing terminals."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal


def mos(device):
    return 'nfet' in device['model'] or 'pfet' in device['model']


def signature(device):
    if set(device['params']) != {'w', 'l'} or len(device['nodes']) != 4:
        raise ValueError('Only four-terminal W/L MOS fingers can share a bank')
    w, l = [Decimal(device['params'][n]) for n in ['w', 'l']]
    if not w.is_finite() or not l.is_finite() or not 0 < w <= 8 or l <= 0:
        raise ValueError('Require finite positive MOS dimensions and at most 8 um per finger')
    if any(v / Decimal('.005') != (v / Decimal('.005')).to_integral_value() for v in [w, l]):
        raise ValueError('Finger dimensions must retain the 5 nm physical grid')
    return tuple(device['nodes']), device['model'], w, l


def group(devices):
    """Keep non-MOS devices separate and return stable, explicitly tracked banks."""
    if any('nf' in d or 'members' in d for d in devices):
        raise ValueError('Use original unbanked physical fingers exactly once')
    if len({d['name'] for d in devices}) != len(devices):
        raise ValueError('Duplicate physical device identity')
    output = []
    by_key = {}
    for device in devices:
        if not mos(device):
            output.append(dict(deepcopy(device), nf=1, members=[device['name']]))
            continue
        key = signature(device)
        if key not in by_key:
            bank = dict(deepcopy(device), nf=0, members=[])
            by_key[key] = bank
            output.append(bank)
        by_key[key]['nf'] += 1
        by_key[key]['members'].append(device['name'])
    expected = Counter(signature(d) for d in devices if mos(d))
    actual = Counter()
    for bank in output:
        if mos(bank):
            actual[signature(bank)] += bank['nf']
    if actual != expected or sorted(n for b in output for n in b['members']) != sorted(d['name'] for d in devices):
        raise ValueError('Physical bank changed a terminal, model, finger or device identity')
    return output
