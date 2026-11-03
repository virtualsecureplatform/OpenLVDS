#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Handoff from the owned compensation diagnostic to actual source qualification."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from continue_driver_compact_native import owner
from continue_receiver_spec_verified import wait_state
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
NAMESPACE = 'driver_cmfb_lead_source_followup'


def admissible_owner(live, relative, terminal):
    if live.get('MainPID', '0') == '0':
        if terminal:
            return
        raise ValueError('Require live diagnostic owner or bound terminal receipt')
    target = 'scripts/probe_driver_cmfb_lead.py run /work/OpenLVDS/' + relative
    if live.get('ActiveState') != 'active' or target not in live.get('ExecStart', ''):
        raise ValueError('Require the exact compensation diagnostic owner')


def passing_report(source, stage):
    if stage not in ['pilot', 'full']:
        raise ValueError('Unknown source qualification stage')
    report = json.loads((source / 'summary.json').read_text())
    if report.get('manifest_sha256') != sha(source / 'manifest.json'):
        raise ValueError('Source receipt binding changed')
    cases, points, flag = ((6, 3, 'source_pilot_passed') if stage == 'pilot'
        else (30, 15, 'source_waveform_matrix_passed'))
    return (report.get(flag) is True and report.get('required_cases') == cases
        and report.get('required_pvt') == points and report.get('passed_pvt') == points)


def prepare(source, original, unit):
    if not source.is_relative_to(ROOT / 'build/diagnostics/driver_source_pilot'):
        raise ValueError('Use the prepared compensation diagnostic')
    if not original.is_relative_to(ROOT / 'build/diagnostics/driver_shape_source'):
        raise ValueError('Use the completed original source matrix')
    relative = str(source.relative_to(ROOT))
    terminal = (source / 'summary.json').exists()
    if terminal:
        passing_report(source, 'pilot')  # Bind the receipt even when it failed.
    live = owner(unit)
    admissible_owner(live, relative, terminal)
    paths = [source / 'manifest.json', original / 'manifest.json', original / 'summary.json']
    paths += [ROOT / 'scripts' / n for n in [Path(__file__).name,
        'qualify_driver_cmfb_lead_source.py', 'probe_driver_cmfb_lead.py',
        'driver_source_campaign.py', 'continue_driver_compact_native.py',
        'continue_receiver_spec_verified.py', 'dll_campaign.py',
        'receiver_static_diagnosis.py', 'env.sh']]
    identity = dict(source=relative, original=str(original.relative_to(ROOT)), unit=unit,
        owner=live, inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, scope=
        'Resource handoff only. Wait for the exact diagnostic owner and bound '
        'six-case passing receipt; the scientific preparer independently '
        'remeasures it and the original full source matrix. Run six actual '
        'schematic pilots, then independently gate all thirty actual source '
        'cases and verify complete source readiness. Existing two-worker '
        'campaigns lease individual P2/P1 slots, no outer lease or retry. '
        'No physical/native, long-component or PHY admission.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def prepared_path(value, namespace):
    inside = Path(value)
    if (inside.parent != Path('/work/OpenLVDS/build/diagnostics') / namespace
            or re.fullmatch('[0-9a-f]{16}', inside.name) is None):
        raise ValueError('Unexpected prepared source artifact')
    return str(inside.relative_to('/work/OpenLVDS'))


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use prepared compensation-source handoff')
    m = json.loads((out / 'manifest.json').read_text())
    i = m['identity']
    stamp = sha(out / 'manifest.json')
    source = ROOT / i['source']

    def unchanged():
        if (sha(out / 'manifest.json') != stamp or out.name != hashlib.sha256(
                json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
                or any(sha(ROOT / n) != h for n, h in i['inputs'].items())):
            raise ValueError('Compensation source handoff changed')

    def state(status, **extra):
        atomic(out / 'state.json', dict(status=status, qualified_phy=False, **extra))

    def finish(status, **extra):
        capture_manifest(out / 'summary.json', dict(status=status,
            manifest_sha256=stamp, qualified_phy=False, **extra))
        state(status, **extra)

    def call(args, label):
        unchanged()
        with (out / (label + '.log')).open('x') as log:
            result = subprocess.run([str(ROOT / 'scripts/env.sh'), '--ngspice',
                '/usr/bin/python3', 'scripts/qualify_driver_cmfb_lead_source.py'] + args,
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        result.check_returncode()
        unchanged()
        lines = (out / (label + '.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'state.json').exists():
            raise ValueError('Prior compensation source handoff retained')
        while True:
            unchanged()
            terminal = (source / 'summary.json').exists()
            passed = passing_report(source, 'pilot') if terminal else False
            if wait_state(owner(i['unit']), i['owner'], terminal) == 'ready':
                break
            state('waiting_for_compensation_diagnostic')
            time.sleep(20)
        if not passed:
            finish('held_compensation_diagnostic_failed',
                diagnostic_report_sha256=sha(source / 'summary.json'))
            return
        state('preparing_actual_source_pilot')
        pilot = prepared_path(call(['prepare-pilot', i['source'], '--original',
            i['original']], 'prepare-pilot'), 'driver_source_pilot')
        capture_manifest(out / 'prepared-pilot.json', dict(artifact=pilot,
            manifest_sha256=sha(ROOT / pilot / 'manifest.json'), qualified_phy=False))
        state('running_actual_source_pilot', artifact=pilot)
        call(['run', pilot], 'run-pilot')
        if not passing_report(ROOT / pilot, 'pilot'):
            finish('held_actual_source_pilot_failed', artifact=pilot,
                report_sha256=sha(ROOT / pilot / 'summary.json'))
            return
        state('preparing_actual_source_matrix')
        full = prepared_path(call(['prepare-full', pilot], 'prepare-full'), 'driver_shape_source')
        capture_manifest(out / 'prepared-full.json', dict(artifact=full,
            manifest_sha256=sha(ROOT / full / 'manifest.json'), qualified_phy=False))
        state('running_actual_source_matrix', artifact=full)
        call(['run', full], 'run-full')
        passed = passing_report(ROOT / full, 'full')
        if passed:
            call(['verify', full], 'verify-full')
        finish('completed_actual_source_matrix' if passed else 'held_actual_source_matrix_failed',
            artifact=full, source_waveform_matrix_passed=passed,
            report_sha256=sha(ROOT / full / 'summary.json'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--original', type=Path)
    p.add_argument('--producer-unit')
    args = p.parse_args()
    if args.action == 'prepare':
        if args.original is None or not args.producer_unit:
            p.error('--original and --producer-unit required')
        print(prepare(args.artifact.resolve(), args.original.resolve(), args.producer_unit), flush=True)
    else:
        run(args.artifact.resolve())
