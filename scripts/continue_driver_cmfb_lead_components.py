#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Start long components after the native pilot's independent matrix handoff."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from continue_driver_compact_native import owner
from continue_driver_cmfb_lead_source import prepared_path
from continue_driver_cmfb_lead_physical import report, matrix_passed
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'driver_cmfb_lead_component_followup'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
SCIENTIFIC = 'qualify_driver_compact_components.py'


def owned(live, expected):
    if live.get('MainPID', '0') == '0':
        return False
    if live != expected:
        raise ValueError('Live physical/native owner changed')
    return True


def selected(parent, label, namespace):
    value = json.loads((parent / (label + '.json')).read_text())
    relative = prepared_path('/work/OpenLVDS/' + value['artifact'], namespace)
    if value['manifest_sha256'] != sha(ROOT / relative / 'manifest.json'):
        raise ValueError('Scientific handoff selection changed')
    return relative


def ready(parent, pilot):
    if not (parent / 'prepare-native-full.json').exists():
        return False
    full = selected(parent, 'prepare-native-full', 'driver_compact_native')
    matrix = json.loads((ROOT / full / 'manifest.json').read_text())
    if (matrix['identity']['pilot'] != pilot or any(matrix['identity']['inputs'].get(
            pilot + '/' + name) != sha(ROOT / pilot / name) for name in ['manifest.json', 'summary.json'])):
        raise ValueError('Prepared native matrix belongs to another pilot')
    # The controller writes this witness only after the native worker exits
    # and the full-matrix preparer independently verifies all six pilots.
    # The component preparer independently verifies them again before dispatch.
    return matrix_passed(report(ROOT / pilot), 'native_output_pilot_passed', 6, 3)


def prepare(parent, unit):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/driver_cmfb_lead_physical_followup'):
        raise ValueError('Use the compensated physical/native handoff')
    pilot = selected(parent, 'prepare-native', 'driver_compact_native_pilot')
    assembled = selected(parent, 'assemble-native', 'driver_compact_native_library')
    live = owner(unit)
    target = 'scripts/continue_driver_cmfb_lead_physical.py run ' + str(parent)
    if live.get('MainPID', '0') == '0':
        if report(parent).get('status') != 'completed_compensated_native_matrix' or not ready(parent, pilot):
            raise ValueError('Require the completed verified native handoff')
    elif live.get('ActiveState') != 'active' or target not in live.get('ExecStart', ''):
        raise ValueError('Require the exact live physical/native handoff owner')
    paths = [parent / n for n in ['manifest.json', 'prepare-native.json', 'assemble-native.json']]
    paths += [ROOT / p / 'manifest.json' for p in [pilot, assembled]]
    paths += [ROOT / 'scripts' / n for n in [Path(__file__).name, SCIENTIFIC,
        'continue_driver_cmfb_lead_physical.py', 'continue_driver_cmfb_lead_source.py',
        'continue_driver_compact_native.py', 'dll_campaign.py', 'receiver_static_diagnosis.py', 'env.sh']]
    identity = dict(parent=str(parent.relative_to(ROOT)), pilot=pilot, assembly=assembled,
        unit=unit, owner=live, inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, scope=
        'Resource handoff only. The exact live physical/native owner and its '
        'independently prepared full native matrix witness must establish the '
        'six-case native pilot pass. Independently reverify the matched pilot '
        'and assembly before all thirty original 2.54 us component fixtures. '
        'Existing two P1 workers share the six-engine dispatcher with the '
        'full native output matrix; no outer lease, retry or partial admission. '
        'Verify all thirty component results before completion. No coupled '
        'payload, DLL, long-training, reliability or PHY release.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use prepared compensated component handoff')
    m = json.loads((out / 'manifest.json').read_text())
    i, stamp = m['identity'], sha(out / 'manifest.json')
    parent = ROOT / i['parent']

    def unchanged():
        if (sha(out / 'manifest.json') != stamp or out.name != hashlib.sha256(
                json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
                or any(sha(ROOT / n) != h for n, h in i['inputs'].items())):
            raise ValueError('Compensated component handoff changed')

    def state(status, **extra):
        atomic(out / 'state.json', dict(status=status, qualified_phy=False, **extra))

    def finish(status, **extra):
        capture_manifest(out / 'summary.json', dict(status=status,
            manifest_sha256=stamp, qualified_phy=False, **extra))
        state(status, **extra)

    def call(args, label):
        unchanged()
        with (out / (label + '.log')).open('x') as log:
            result = subprocess.run([str(ROOT / 'scripts/env.sh'), '--tools', '--ngspice',
                '/usr/bin/python3', 'scripts/' + SCIENTIFIC] + args,
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        result.check_returncode()
        unchanged()
        lines = (out / (label + '.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'state.json').exists():
            raise ValueError('Prior compensated component handoff retained')
        while True:
            unchanged()
            live = owned(owner(i['unit']), i['owner'])
            terminal = (parent / 'summary.json').exists()
            if terminal:
                terminal = report(parent)
                if terminal.get('status') != 'completed_compensated_native_matrix':
                    finish('held_native_prerequisite_failed', parent_report_sha256=sha(parent / 'summary.json'))
                    return
            elif not live:
                raise ValueError('Native owner ended without terminal scientific evidence')
            if ready(parent, i['pilot']):
                break
            if not live:
                raise ValueError('Native owner ended without the complete pilot handoff')
            state('waiting_for_verified_native_pilot')
            time.sleep(20)
        state('preparing_long_components')
        components = prepared_path(call(['prepare', i['pilot'], '--assembly', i['assembly']],
            'prepare'), 'driver_compact_components')
        capture_manifest(out / 'prepared.json', dict(artifact=components,
            manifest_sha256=sha(ROOT / components / 'manifest.json'), qualified_phy=False))
        state('running_long_components', artifact=components)
        call(['run', components], 'run')
        result = report(ROOT / components)
        passed = result.get('passed') is True and result.get('required') == 30 and result.get('passed_cases') == 30
        if passed:
            call(['verify', components], 'verify')
        finish('completed_long_components' if passed else 'held_long_components_failed',
            artifact=components, components_passed=passed,
            report_sha256=sha(ROOT / components / 'summary.json'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--producer-unit')
    args = p.parse_args()
    if args.action == 'prepare':
        if not args.producer_unit:
            p.error('--producer-unit required')
        print(prepare(args.artifact.resolve(), args.producer_unit), flush=True)
    else:
        run(args.artifact.resolve())
