#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Advance both admitted gain/balance variants independently with unchanged scientific producers."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
UNIT = 'openlvds-receiver-gain-balance-clock-followup.service'
REFERENCE = Path('build/diagnostics/receiver_layout/74f1d1fd9724608e')
PARENT = Path('build/diagnostics/clock_restore/50565a94b3b04171')
VARIANTS = ['restore_p4_n8', 'decision_pair_w32']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def owner():
    p = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=MainPID,ActiveState,InvocationID'],
        check=True, capture_output=True, text=True)
    return dict(line.split('=', 1) for line in p.stdout.splitlines())


def prepare(matrix):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/receiver_gain_balance_matrix'):
        raise ValueError('Use the prepared gain/balance source matrix')
    live = owner()
    if live['ActiveState'] != 'active' or live['MainPID'] == '0':
        raise ValueError('Require the exact live source-clock followup owner')
    paths = [matrix/'manifest.json', matrix/'clock_followup/manifest.json', matrix/'clock_followup/run.py']
    paths += [ROOT/'scripts'/n for n in [NAME, 'env.sh', 'layout_receiver_gain_balance.py',
        'probe_receiver_gain_balance.py', 'receiver_gain_balance_clock.py', 'receiver_candidate_rc.py', 'receiver_soft_frontend_geometry.py']]
    paths += [ROOT/REFERENCE/n for n in ['summary.json', 'candidate.spice', 'extraction.json', 'rc_audit.json']]
    paths += [ROOT/PARENT/'manifest.json']
    identity = dict(matrix=str(matrix.relative_to(ROOT)), owner=live, unit=UNIT, max_parallel_variants=2, no_outer_lease=True,
        reference=str(REFERENCE), replay_parent=str(PARENT), qualified_phy=False,
        files={str(p.relative_to(ROOT)): sha(p) for p in paths},
        scope='Two independent variant handoffs, at most two variants, actual scientific SPICE leases only. Resource handoff only. Original scientific DC/clock, DRC/LVS, extraction/RC audit and native transport gates remain authoritative. No automatic component, selected-PHY or release promotion.')
    out = ROOT/'build/diagnostics/receiver_physical_followup'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True); capture_manifest(out/'manifest.json', identity)
    return out


def admitted_clock(matrix, variant, result):
    if variant not in VARIANTS or result.get('variant') != variant:
        raise ValueError('Clock result variant binding changed')
    relative = Path(result['root'])
    if relative.is_absolute() or '..' in relative.parts or not relative.is_relative_to('build/diagnostics/receiver_clamp'):
        raise ValueError('Unexpected source-clock result path')
    clock = ROOT/relative; admission = clock/'source_clock_admission.json'
    if result.get('returncode') != 0 or result.get('admission', {}).get('source_clock_passed') is not True:
        return None
    if sha(admission) != result['admission_sha256'] or json.loads(admission.read_text()) != result['admission']:
        raise ValueError('Source-clock admission bytes changed')
    m = json.loads((clock/'manifest.json').read_text())
    if (m['identity'].get('gain_balance_variant') != variant or
            m['identity'].get('static_screen') != str(matrix.relative_to(ROOT)) or
            result['admission'].get('manifest_sha256') != sha(clock/'manifest.json') or
            result['admission'].get('report_sha256') != sha(clock/'summary.json')):
        raise ValueError('Source-clock evidence differs from selected variant/matrix/report')
    return relative


def native_result(root):
    m = json.loads((root/'manifest.json').read_text()); s = json.loads((root/'summary.json').read_text())
    if s.get('manifest_sha256') != sha(root/'manifest.json') or s.get('diagnostic_complete') is not True:
        raise ValueError('Native replay did not complete its exact manifest')
    if len(m['tasks']) != 2 or {t['id'] for t in m['tasks']} != {'captured', 'sharp_control'}:
        raise ValueError('Both original native controls are required')
    return dict(native_clock_passed=s.get('native_clock_passed') is True, qualified_phy=False,
        root=str(root.relative_to(ROOT)), manifest_sha256=sha(root/'manifest.json'), report_sha256=sha(root/'summary.json'))


def dispatch(variants, execute):
    if not variants or len(variants) != len(set(variants)) or any(v not in VARIANTS for v in variants):
        raise ValueError('Select each admitted variant at most once')
    # Every worker launches isolated scientific subprocesses. Their internal
    # shared-slot leases remain the sole limit on actual simultaneous SPICE.
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(execute, variants))


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_physical_followup'):
        raise ValueError('Use a prepared gain/balance physical followup')
    m = json.loads((out/'manifest.json').read_text()); stamp = sha(out/'manifest.json')
    def unchanged():
        if sha(out/'manifest.json') != stamp or any(sha(ROOT/n) != h for n, h in m['files'].items()):
            raise ValueError('Physical handoff context changed')
    def waiting(expected, variant=None):
        unchanged(); live = owner()
        if live != m['owner']:
            if expected.is_file():
                return  # Completion may race the owner's final state change.
            raise ValueError('Exact source-clock owner terminated or changed before required evidence')
        atomic(out/((variant+'_state.json') if variant else 'state.json'), dict(status='waiting_for_source_clocks', owner=live, qualified_phy=False))
        time.sleep(20)
    def command(args, label, tools=False):
        unchanged()
        cmd = [str(ROOT/'scripts/env.sh')]+(['--tools'] if tools else [])+['--ngspice', '/usr/bin/python3']+args
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        (out/(label+'.log')).write_text(p.stdout+p.stderr); p.check_returncode(); unchanged()
        return p.stdout.strip().splitlines()[-1]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        if (out/'state.json').exists() or (out/'summary.json').exists():
            raise ValueError('Prior physical followup retained; do not repeat orchestration')
        matrix = ROOT/m['matrix']; followup = matrix/'clock_followup'
        try:
            while not (matrix/'summary.json').is_file():
                waiting(matrix/'summary.json')
            screen = json.loads((matrix/'summary.json').read_text())
            variants = [v for v in VARIANTS if screen['variants'][v]['source_dc_passed'] is True]
            if m.get('max_parallel_variants') != 2 or m.get('no_outer_lease') is not True:
                raise ValueError('Require two independent variants and no outer simulation lease')
            atomic(out/'state.json', dict(status='running_variant_handoffs', variants=variants, qualified_phy=False))
            def evaluate(variant):
                receipt = followup/(variant+'_result.json')
                while not receipt.is_file():
                    waiting(receipt, variant)
                r = json.loads(receipt.read_text()); clock = admitted_clock(matrix, variant, r)
                if clock is None:
                    return dict(variant=variant, status='held_source_clock_failed', qualified_phy=False)
                atomic(out/(variant+'_state.json'), dict(status='building_geometry', variant=variant, qualified_phy=False))
                row = json.loads(command(['scripts/layout_receiver_gain_balance.py', m['reference'],
                    '--dc-matrix', m['matrix'], '--source-clock', str(clock), '--variant', variant], variant+'_layout', tools=True))
                layout = Path(row['output'])
                if row.get('passed') is not True or not layout.is_relative_to('/work/OpenLVDS/build/diagnostics/receiver_layout'):
                    raise ValueError('Physical builder did not produce passing isolated geometry')
                layout = layout.relative_to('/work/OpenLVDS')
                command(['scripts/receiver_candidate_rc.py', str(layout)], variant+'_extraction', tools=True)
                atomic(out/(variant+'_state.json'), dict(status='preparing_native', variant=variant, layout=str(layout), qualified_phy=False))
                replay = Path(command(['scripts/probe_receiver_gain_balance.py', 'prepare', m['replay_parent'], str(layout),
                    '--dc-matrix', m['matrix'], '--source-clock', str(clock), '--variant', variant], variant+'_native_prepare'))
                if not replay.is_relative_to('/work/OpenLVDS/build/diagnostics/receiver_replay'):
                    raise ValueError('Unexpected native replay context')
                replay = replay.relative_to('/work/OpenLVDS')
                capture_manifest(out/(variant+'_prepared.json'), dict(variant=variant, clock=str(clock),
                    layout=str(layout), replay=str(replay), clock_receipt_sha256=sha(receipt), qualified_phy=False))
                atomic(out/(variant+'_state.json'), dict(status='running_native', variant=variant, replay=str(replay), qualified_phy=False))
                # The native producer independently leases its two simulations.
                command(['scripts/probe_receiver_gain_balance.py', 'run', str(replay)], variant+'_native_run')
                result = dict(native_result(ROOT/replay), variant=variant, layout=str(layout))
                return result
            def execute(variant):
                try:
                    result = evaluate(variant)
                except Exception as error:
                    result = dict(variant=variant, status='held_for_diagnosis', error=str(error), qualified_phy=False)
                capture_manifest(out/(variant+'_result.json'), result)
                atomic(out/(variant+'_state.json'), dict(status='completed_native_diagnostic' if result.get('native_clock_passed') is True else 'held_for_diagnosis', qualified_phy=False))
                return result
            results = dispatch(variants, execute)
            unchanged()
            passed = bool(results and all(r.get('native_clock_passed') is True for r in results))
            capture_manifest(out/'summary.json', dict(results=results, qualified_phy=False,
                native_clock_passed=passed, manifest_sha256=stamp, scope=m['scope']))
            atomic(out/'state.json', dict(status='completed_native_diagnostic' if passed else 'held_for_diagnosis', qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
