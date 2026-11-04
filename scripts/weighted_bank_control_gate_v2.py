# SPDX-License-Identifier: GPL-3.0-only
"""Require the independently verified physical fine-control repair before a bank run."""
import hashlib
import json
import verify_weighted_fine_control_v3 as verification

ROOT=verification.ROOT
sha=verification.pilot.sha


def eligible(groups):
    guarded=[g for g in groups if g['mode']=='guarded']
    return (len(guarded)==1 and guarded[0]['data_bias_cases']==2
            and all(guarded[0][key] is True for key in
                    ['component_pilot_passed','control_settling_passed','terminal_screen_passed'])
            and 0<=guarded[0]['maximum_terminal_difference_v']<=1.95)


def require(receipt,clock,fines):
    report=json.loads((receipt/'summary.json').read_text());i=report['identity']
    if (receipt.parent!=ROOT/'build/diagnostics/weighted_fine_control_verification_v3'
        or i['version']!=verification.VERSION
        or receipt.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or report['all_declared_raw_waveforms_verified'] is not True):
        raise ValueError('Require an unchanged independent physical fine-control receipt')
    parent=ROOT/i['parent'];m=verification.pilot.bound(parent);pi=m['identity']
    if pi['clock']!=str(clock.relative_to(ROOT)) or pi['fine_cells']!=str(fines.relative_to(ROOT)):
        raise ValueError('Fine-control repair uses different native components')
    state=json.loads((parent/'state.json').read_text());rows=json.loads((parent/'summary.json').read_text())['rows']
    if (state['status']!='fine_control_pilot_complete' or state['cases']!=4 or state['errors']
        or [r['task'] for r in rows]!=m['tasks'] or any(r['error'] is not None for r in rows)):
        raise ValueError('Require four complete error-free physical fine-control cases')
    groups=verification.assess(rows)
    if groups!=report['groups'] or not eligible(groups):
        raise ValueError('The guarded physical fine-control repair has not passed both DATA biases')
    return dict(receipt=str(receipt.relative_to(ROOT)),sha256=sha(receipt/'summary.json'),
                parent=str(parent.relative_to(ROOT)),guarded_profile_passed=True,qualified_phy=False)
