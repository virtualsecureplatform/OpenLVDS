# SPDX-License-Identifier: GPL-3.0-only
"""Group identical physical fingers for compact PCells without changing terminals."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import re


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


def pcell_parameters(bank):
    """Pinned Magic MOS recipe: separate gate contacts, one guarded row."""
    if not mos(bank):
        raise ValueError('Use a MOS bank for the multi-finger PCell recipe')
    signature(bank)
    nf = bank.get('nf')
    if (not isinstance(nf, int) or isinstance(nf, bool) or nf < 1 or
            len(bank.get('members', [])) != nf or len(set(bank['members'])) != nf):
        raise ValueError('Invalid physical bank membership/count')
    return dict(bank['params'], nf=nf, m=1, conn_gates=0, guard=1,
                botc=0, full_metal=1, doports=1)


def terminal_groups(ports, nf):
    """Require every separately exposed gate; leave D/S contacts distinct."""
    if not isinstance(nf, int) or isinstance(nf, bool) or nf < 1:
        raise ValueError('Invalid PCell finger count')
    roles = {name: [] for name in ['D', 'G', 'S', 'B']}
    for name in ports:
        if name == 'B':
            roles['B'].append(name)
            continue
        match = re.fullmatch(r'([DGS])(\d*)', name)
        if (match is None or (not match[2] and nf != 1) or
                (match[2] and not 0 <= int(match[2]) < nf)):
            raise ValueError('Unexpected physical PCell terminal: ' + name)
        roles[match[1]].append(name)
    expected_gates = {'G'} if nf == 1 else {f'G{i}' for i in range(nf)}
    if (set(roles['G']) != expected_gates or len(roles['B']) != 1 or
            not roles['D'] or not roles['S']):
        raise ValueError('Missing separate gate, drain, source or bulk contacts')
    return {role: sorted(names) for role, names in roles.items()}
