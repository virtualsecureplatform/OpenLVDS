#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Advance a passing compensated source matrix through physical and native gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from continue_driver_cmfb_lead_source import prepared_path
from continue_driver_compact_native import owner
from continue_receiver_spec_verified import wait_state
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'driver_cmfb_lead_physical_followup'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
BUILD = 'build_driver_cmfb_lead.py'
EXTRACT = 'extract_driver_compact.py'
ASSEMBLE = 'assemble_driver_compact_native.py'
PREPARE = 'prepare_driver_cmfb_lead_native.py'
PILOT = 'probe_driver_compact_native.py'
FULL = 'qualify_driver_compact_native.py'


def admissible_owner(live, source_handoff, terminal):
    if live.get('MainPID', '0') == '0':
        if terminal:
            return
        raise ValueError('Require live source handoff owner or bound terminal evidence')
    target = 'scripts/continue_driver_cmfb_lead_source.py run ' + str(source_handoff)
    if live.get('ActiveState') != 'active' or target not in live.get('ExecStart', ''):
        raise ValueError('Require the exact source-matrix handoff owner')


def report(source):
    value = json.loads((source / 'summary.json').read_text())
    if value.get('manifest_sha256') != sha(source / 'manifest.json'):
        raise ValueError('Scientific receipt binding changed')
    return value


def matrix_passed(value, flag, cases, points):
    return (value.get(flag) is True and value.get('required_cases') == cases
        and value.get('required_pvt') == points and value.get('passed_pvt') == points)


def prepare(source, handoff, tiles, unit):
    for path, namespace in [(source, 'driver_shape_source'), (handoff, 'driver_cmfb_lead_source_followup'),
                            (tiles, 'driver_inverter_tiles')]:
        if not path.is_relative_to(ROOT / 'build/diagnostics' / namespace):
            raise ValueError('Use the declared compensated source, handoff and tile namespaces')
    m = json.loads((source / 'manifest.json').read_text())
    selected = json.loads((handoff / 'prepared-full.json').read_text())
    relative = str(source.relative_to(ROOT))
    if (m['identity'].get('stage') != 'full'
            or m['identity'].get('recipe') != 'cmfb_lead_one_direct_five_series_r0p35_l1p25_actual_schematic'
            or selected.get('artifact') != relative
            or selected.get('manifest_sha256') != sha(source / 'manifest.json')):
        raise ValueError('Source handoff did not select this actual compensated matrix')
    terminal = (source / 'summary.json').exists()
    if terminal:
        report(source)
    live = owner(unit)
    admissible_owner(live, handoff, terminal)
    paths = [source / 'manifest.json', handoff / 'manifest.json', handoff / 'prepared-full.json',
        tiles / 'summary.json']
    paths += [ROOT / 'scripts' / name for name in [Path(__file__).name, BUILD, EXTRACT,
        ASSEMBLE, PREPARE, PILOT, FULL, 'qualify_driver_cmfb_lead_source.py',
        'continue_driver_cmfb_lead_source.py', 'continue_driver_compact_native.py',
        'continue_receiver_spec_verified.py', 'dll_campaign.py', 'receiver_static_diagnosis.py', 'env.sh']]
    identity = dict(source=relative, source_handoff=str(handoff.relative_to(ROOT)),
        tiles=str(tiles.relative_to(ROOT)), unit=unit, owner=live,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, scope=
        'Resource handoff only: exact source owner must terminate with all thirty '
        'actual schematic cases passing and independently verified. Build the new '
        '321-device layout, require zero DRC and strict LVS, audit native RC, '
        'assemble native shared bias, prepare/run all six compensated native '
        'pilots, then independently gate all thirty native output cases and '
        'verify them. Stop at any failed stage; no retry or outer SPICE lease. '
        'Scientific children use the existing individual six-slot dispatcher. '
        'No long-component, reliability, coupled link or PHY release.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def source_readiness(source, handoff):
    finished = report(handoff)
    if (finished.get('status') != 'completed_actual_source_matrix'
            or finished.get('source_waveform_matrix_passed') is not True
            or finished.get('artifact') != str(source.relative_to(ROOT))
            or finished.get('report_sha256') != sha(source / 'summary.json')):
        raise ValueError('Require the successful bound source-verification handoff')
    lines = (handoff / 'verify-full.log').read_text().strip().splitlines()
    path = Path(lines[-1])
    if path.name != 'summary.json':
        raise ValueError('Unexpected actual-source readiness receipt')
    relative = prepared_path(str(path.parent), 'driver_cmfb_lead_source_verification') + '/summary.json'
    ready = json.loads((ROOT / relative).read_text())
    if ready.get('campaign') != str(source.relative_to(ROOT)):
        raise ValueError('Readiness receipt selects another source matrix')
    return relative


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use prepared compensated physical handoff')
    m = json.loads((out / 'manifest.json').read_text())
    i, stamp = m['identity'], sha(out / 'manifest.json')
    source = ROOT / i['source']

    def unchanged():
        if (sha(out / 'manifest.json') != stamp or out.name != hashlib.sha256(
                json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
                or any(sha(ROOT / n) != h for n, h in i['inputs'].items())):
            raise ValueError('Compensated physical handoff changed')

    def state(status, **extra):
        atomic(out / 'state.json', dict(status=status, qualified_phy=False, **extra))

    def finish(status, artifact):
        capture_manifest(out / 'summary.json', dict(status=status, artifact=artifact,
            manifest_sha256=stamp, report_sha256=sha(ROOT / artifact / 'summary.json'), qualified_phy=False))
        state(status, artifact=artifact)

    def call(script, args, label):
        unchanged()
        with (out / (label + '.log')).open('x') as log:
            result = subprocess.run([str(ROOT / 'scripts/env.sh'), '--tools', '--ngspice',
                '/usr/bin/python3', 'scripts/' + script] + args,
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        result.check_returncode()
        unchanged()
        lines = (out / (label + '.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''

    def artifact(script, args, label, namespace):
        relative = prepared_path(call(script, args, label), namespace)
        capture_manifest(out / (label + '.json'), dict(artifact=relative,
            manifest_sha256=sha(ROOT / relative / 'manifest.json'), qualified_phy=False))
        return relative

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'state.json').exists():
            raise ValueError('Prior compensated physical handoff retained')
        while True:
            unchanged()
            terminal = (source / 'summary.json').exists()
            source_report = report(source) if terminal else None
            if wait_state(owner(i['unit']), i['owner'], terminal) == 'ready':
                break
            state('waiting_for_full_actual_source_matrix')
            time.sleep(20)
        if not matrix_passed(source_report, 'source_waveform_matrix_passed', 30, 15):
            finish('held_actual_source_matrix_failed', i['source'])
            return
        ready = source_readiness(source, ROOT / i['source_handoff'])
        state('building_compensated_layout')
        layout = artifact(BUILD, [ready, '--tiles', i['tiles']], 'build-layout', 'driver_compact_layout')
        physical = json.loads((ROOT / layout / 'summary.json').read_text())
        core = physical['designs']['openlvds_driver_core']
        if not (physical.get('passed') is True and core.get('passed') is True
                and core.get('drc_count') == '0' and core.get('lvs_passed') is True):
            finish('held_compensated_layout_failed', layout)
            return
        state('extracting_compensated_layout', artifact=layout)
        extraction = artifact(EXTRACT, [layout], 'extract-layout', 'driver_compact_extraction')
        rc = json.loads((ROOT / extraction / 'summary.json').read_text())
        if not (rc.get('passed') is True and rc['rc_audit'].get('passed') is True):
            finish('held_compensated_rc_audit_failed', extraction)
            return
        state('assembling_compensated_native_bias')
        assembled = artifact(ASSEMBLE, [extraction], 'assemble-native', 'driver_compact_native_library')
        state('preparing_compensated_native_pilot')
        pilot = artifact(PREPARE, [assembled], 'prepare-native', 'driver_compact_native_pilot')
        state('running_compensated_native_pilot', artifact=pilot)
        call(PILOT, ['run', pilot], 'run-native-pilot')
        if not matrix_passed(report(ROOT / pilot), 'native_output_pilot_passed', 6, 3):
            finish('held_compensated_native_pilot_failed', pilot)
            return
        state('preparing_compensated_native_matrix')
        full = artifact(FULL, ['prepare', pilot], 'prepare-native-full', 'driver_compact_native')
        state('running_compensated_native_matrix', artifact=full)
        call(FULL, ['run', full], 'run-native-full')
        if not matrix_passed(report(ROOT / full), 'native_output_matrix_passed', 30, 15):
            finish('held_compensated_native_matrix_failed', full)
            return
        call(FULL, ['verify', full], 'verify-native-full')
        finish('completed_compensated_native_matrix', full)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--source-handoff', type=Path)
    p.add_argument('--tiles', type=Path)
    p.add_argument('--producer-unit')
    args = p.parse_args()
    if args.action == 'prepare':
        if args.source_handoff is None or args.tiles is None or not args.producer_unit:
            p.error('--source-handoff, --tiles and --producer-unit required')
        print(prepare(args.artifact.resolve(), args.source_handoff.resolve(),
            args.tiles.resolve(), args.producer_unit), flush=True)
    else:
        run(args.artifact.resolve())
