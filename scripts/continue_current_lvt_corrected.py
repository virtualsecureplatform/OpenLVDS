#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the prepared 110:1 link child after preserving a stalled 100:1 control."""
import argparse
import fcntl
import json
from pathlib import Path

import compare_current_lvt_link as link
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
SCOPE = ('Corrected 110:1 child only, with its already prepared source, native '
         'driver, bias, digital RX, channel, stimuli and numerical policy. '
         'The stalled 100:1 control is inconclusive. This does not complete '
         'the paired comparison or supply component, native-RX, startup, '
         'sampling-margin or PHY admission.')


def validate(pair):
    if not pair.is_relative_to(ROOT/'build/diagnostics/current_lvt_link'):
        raise ValueError('Use a prepared matched current/LVT link pair')
    if not (pair/'retirement.json').is_file():
        raise ValueError('Preserve and retire the stalled control before standalone dispatch')
    retired = json.loads((pair/'retirement.json').read_text())
    receipt = ROOT/retired['receipt']
    if not receipt.is_relative_to(ROOT/'build/diagnostics/resident_jobs'):
        raise ValueError('Use the bound process-retirement receipt')
    after = json.loads(receipt.read_text()); before_path = receipt.with_name('before_stop.json')
    before = json.loads(before_path.read_text())
    if (after != {k: v for k, v in retired.items() if k != 'receipt'} or
            after.get('all_old_processes_gone') is not True or
            after.get('all_archived_files_unchanged') is not True or
            after.get('control_electrically_inconclusive') is not True or
            after.get('paired_comparison_complete') is not False or
            after['unit']['MainPID'] != '0'):
        raise ValueError('Stalled control retirement is incomplete or changed')
    sha = link.pilot.digest
    if before['files'].get(str((pair/'manifest.json').relative_to(ROOT))) != sha(pair/'manifest.json'):
        raise ValueError('Retirement receipt belongs to another comparison')
    if any(sha(ROOT/n) != h for n, h in before['files'].items()):
        raise ValueError('Preserved control/producer/fixture bytes changed')
    m = json.loads((pair/'manifest.json').read_text()); i = m['identity']
    children = i['children']
    if len(children) != 2 or [c['current_ratio'] for c in children] != [100, 110]:
        raise ValueError('Require the original matched 100:1/110:1 pair')
    if (any(sha(ROOT/n) != h for n, h in dict(i['inputs'], **i['source_proofs']).items()) or
            any(sha(ROOT/c['root']/'manifest.json') != c['manifest_sha256'] for c in children)):
        raise ValueError('Prepared source admission or child context changed')
    child = ROOT/children[1]['root']
    if not child.is_relative_to(ROOT/'build/diagnostics/analog_link_pilot'):
        raise ValueError('Unexpected prepared corrected-child namespace')
    return child, receipt, before_path


def run(pair):
    child, receipt, before = validate(pair)
    if not (child/'summary.json').exists() and any((child/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
        raise ValueError('Partial corrected-child output retained; use a fresh context')
    out = pair/'corrected_child_followup'; out.mkdir(exist_ok=True)
    sha = link.pilot.digest
    identity = dict(pair_manifest_sha256=sha(pair/'manifest.json'), child=str(child.relative_to(ROOT)),
        child_manifest_sha256=sha(child/'manifest.json'), receipt_sha256=sha(receipt), before_stop_sha256=sha(before),
        producer_sha256=sha(Path(__file__)), global_slot_budget=6, priority=1,
        max_jobs=1, no_outer_lease=True, scope=SCOPE)
    capture_manifest(out/'manifest.json', identity)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            atomic(out/'state.json', dict(status='running_corrected_child', qualified_phy=False,
                control_electrically_inconclusive=True, paired_comparison_complete=False))
            with link.profile(True):
                # Original frozen science owns its child lock, context hashes,
                # fair lease, partial-output guard and full-wave measurements.
                link.pilot.run(child)
            validate(pair)
            result = json.loads((child/'summary.json').read_text())
            report = dict(diagnostic_complete=result['diagnostic_complete'], corrected_child_only=True,
                paired_comparison_complete=False, control_electrically_inconclusive=True, qualified_phy=False,
                child_report_sha256=sha(child/'summary.json'), metrics=result['metrics'], scope=SCOPE)
            capture_manifest(out/'summary.json', report)
            atomic(out/'state.json', dict(status='corrected_child_complete', qualified_phy=False,
                paired_comparison_complete=False, control_electrically_inconclusive=True))
        except Exception as error:
            atomic(out/'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False,
                paired_comparison_complete=False, control_electrically_inconclusive=True))
            raise
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('pair', type=Path); a = p.parse_args()
    run(a.pair.resolve()); print(a.pair.resolve()/'corrected_child_followup/summary.json', flush=True)
