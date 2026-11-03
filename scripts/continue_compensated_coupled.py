#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join matched native/component owners before the gated coupled diagnostic."""
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
from continue_receiver_spec_verified import wait_state
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'compensated_coupled_followup'
SCIENTIFIC = 'restore_compensated_coupled.py'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def prerequisites(native, component):
    if not matrix_passed(native, 'native_output_matrix_passed', 30, 15):
        return False
    return component.get('passed') is True and component.get('required') == 30 and component.get('passed_cases') == 30


def selection(parent, receipt, namespace):
    value = json.loads((parent / receipt).read_text())
    relative = prepared_path('/work/OpenLVDS/' + value['artifact'], namespace)
    if value['manifest_sha256'] != sha(ROOT / relative / 'manifest.json'):
        raise ValueError('Qualification handoff selection changed')
    return relative


def prepare(native_handoff, component_handoff, native_unit, component_unit, reference, receiver):
    specs = [('native', native_handoff, native_unit, 'driver_cmfb_lead_physical_followup',
        'prepare-native-full.json', 'driver_compact_native', 'continue_driver_cmfb_lead_physical.py'),
        ('components', component_handoff, component_unit, 'driver_cmfb_lead_component_followup',
        'prepared.json', 'driver_compact_components', 'continue_driver_cmfb_lead_components.py')]
    sources, paths = {}, []
    for label, parent, unit, namespace, selected, child_namespace, script in specs:
        if not parent.is_relative_to(ROOT / 'build/diagnostics' / namespace):
            raise ValueError('Use the exact matched qualification handoffs')
        artifact = selection(parent, selected, child_namespace)
        live = owner(unit)
        target = 'scripts/' + script + ' run ' + str(parent)
        if live.get('MainPID', '0') == '0':
            report(parent)
            report(ROOT / artifact)
        elif live.get('ActiveState') != 'active' or target not in live.get('ExecStart', ''):
            raise ValueError('Require the exact native/component qualification owners')
        sources[label] = dict(parent=str(parent.relative_to(ROOT)), artifact=artifact, unit=unit, owner=live)
        paths += [parent / 'manifest.json', parent / selected, ROOT / artifact / 'manifest.json']
    manifests = {label: json.loads((ROOT / source['artifact'] / 'manifest.json').read_text())
        for label, source in sources.items()}
    if manifests['native']['identity']['pilot'] != manifests['components']['identity']['pilot']:
        raise ValueError('Qualification handoffs select different native pilots')
    if (not reference.is_relative_to(ROOT / 'build/diagnostics/ltra_exact_tx_benchmark')
            or not receiver.is_relative_to(ROOT / 'build/diagnostics/receiver_spec_rc')):
        raise ValueError('Use the validated exact-TX and preferred receiver RC evidence')
    paths += [reference / n for n in ['manifest.json', 'summary.json', 'comparison.json']]
    paths += [receiver / n for n in ['manifest.json', 'summary.json']]
    paths += [ROOT / 'scripts' / n for n in [Path(__file__).name, SCIENTIFIC,
        'continue_driver_compact_native.py', 'continue_driver_cmfb_lead_source.py',
        'continue_driver_cmfb_lead_physical.py', 'continue_receiver_spec_verified.py',
        'dll_campaign.py', 'receiver_static_diagnosis.py', 'env.sh']]
    identity = dict(sources=sources, reference=str(reference.relative_to(ROOT)),
        receiver=str(receiver.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        scope='Resource handoff only. Both exact qualification owners must terminate '
        'with bound successful scientific and controller receipts. Independently '
        'verify the complete matched native output and long-component matrices '
        'in the coupled preparer, then run a fresh short and original full payload '
        'diagnostic. No retry or outer lease; existing six-engine dispatcher. '
        'Completed data is independently verified even if payload transport fails. '
        'No actual DLL, long-training, aperture margin, all-link or PHY release.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def terminal_source(source, label):
    artifact, parent = ROOT / source['artifact'], ROOT / source['parent']
    scientific = report(artifact) if (artifact / 'summary.json').exists() else None
    terminal = scientific is not None and (parent / 'summary.json').exists()
    state = wait_state(owner(source['unit']), source['owner'], terminal)
    if state != 'ready':
        return None
    controller = report(parent)
    expected = 'completed_compensated_native_matrix' if label == 'native' else 'completed_long_components'
    if (controller.get('status') != expected or controller.get('artifact') != source['artifact']
            or controller.get('report_sha256') != sha(artifact / 'summary.json')):
        return False
    return scientific


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use prepared matched coupled handoff')
    m = json.loads((out / 'manifest.json').read_text())
    i, stamp = m['identity'], sha(out / 'manifest.json')

    def unchanged():
        if (sha(out / 'manifest.json') != stamp or out.name != hashlib.sha256(
                json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
                or any(sha(ROOT / n) != h for n, h in i['inputs'].items())):
            raise ValueError('Matched coupled handoff changed')

    def state(status, **extra):
        atomic(out / 'state.json', dict(status=status, qualified_phy=False, **extra))

    def finish(status, **extra):
        capture_manifest(out / 'summary.json', dict(status=status, manifest_sha256=stamp,
            qualified_phy=False, **extra))
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
            raise ValueError('Prior matched coupled handoff retained')
        while True:
            unchanged()
            values = {label: terminal_source(source, label) for label, source in i['sources'].items()}
            if any(v is False for v in values.values()):
                finish('held_qualification_owner_failed')
                return
            if all(v is not None for v in values.values()):
                if not prerequisites(values['native'], values['components']):
                    finish('held_qualification_matrix_failed')
                    return
                break
            state('waiting_for_matched_qualifications')
            time.sleep(20)
        state('preparing_coupled_diagnostic')
        artifact = prepared_path(call(['prepare', i['sources']['native']['artifact'], '--components',
            i['sources']['components']['artifact'], '--reference', i['reference'], '--receiver-rc', i['receiver']],
            'prepare'), 'compensated_coupled_restoration')
        capture_manifest(out / 'prepared.json', dict(artifact=artifact,
            manifest_sha256=sha(ROOT / artifact / 'manifest.json'), qualified_phy=False))
        state('running_coupled_diagnostic', artifact=artifact)
        call(['run', artifact], 'run')
        result = report(ROOT / artifact)
        rows = result.get('results', [])
        complete = len(rows) == 2 and all(r.get('numerically_completed') is True and r.get('error') is None for r in rows)
        if complete:
            call(['verify', artifact], 'verify')
        restored = complete and result.get('payload_restored') is True
        finish('completed_coupled_diagnostic' if restored else 'held_coupled_diagnostic', artifact=artifact,
            payload_restored=restored, report_sha256=sha(ROOT / artifact / 'summary.json'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--component-handoff', type=Path)
    p.add_argument('--native-unit')
    p.add_argument('--component-unit')
    p.add_argument('--reference', type=Path)
    p.add_argument('--receiver-rc', type=Path)
    args = p.parse_args()
    if args.action == 'prepare':
        if (args.component_handoff is None or not args.native_unit or not args.component_unit
                or args.reference is None or args.receiver_rc is None):
            p.error('Both owner units/handoffs, --reference and --receiver-rc required')
        print(prepare(args.artifact.resolve(), args.component_handoff.resolve(), args.native_unit,
            args.component_unit, args.reference.resolve(), args.receiver_rc.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
