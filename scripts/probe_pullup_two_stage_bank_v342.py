#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify actual full-bank P40 input loading, quarter latency and code overlap."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_two_stage_fine_bank_v322 as source
import probe_loaded_pullup_recovery_v341 as recovery
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
VERSION = 'qualified-p40-loaded-driver-two-stage-native-bank-four-point-screen-v342.1'
CONTEXT = 'pullup_two_stage_bank_v342'
TOP = 'openlvds_pullup_two_stage_fine_v342'
MODEL = recovery.MODEL
sha = source.sha
atomic = source.atomic
SCOPE = ('Only loaded inverter becomes qualified P40/N16 in the actual two-stage '
         'bank; original TG/coarse/fine/control/final-stage components and every '
         'startup event retained; original zero/duty/coarse and overlap gates; '
         'ideal new shared wires, no routed/dense/update/all-PVT/DLL/PHY admission')


def specifications():
    return [dict(s, loaded_driver='p40n16') for s in source.specifications()]


def transform(bank, previous, cell):
    native = source.source.native
    definition = source.source.cell_definition
    defs = native.definitions(bank)
    extra = native.definitions(cell)
    if set(extra) != {MODEL} or extra[MODEL][0] != ['A', 'Y', 'VGND', 'VPWR'] or MODEL in defs:
        raise ValueError('Require the exact qualified P40/N16 component interface')
    before = definition(bank, source.TOP)
    old = ['Xfine_isolate', 'selected', 'fine_node', 'VGND', 'VPWR', source.source.MODEL]
    if [w for w in defs[source.TOP][1] if w[0] == old[0]] != [old]:
        raise ValueError('Original full-bank P20/N16 loaded inverter changed')
    after = before.replace(' '.join(old)+'\n', ' '.join(old[:-1]+[MODEL])+'\n', 1)
    after = after.replace('.subckt '+source.TOP+' ', '.subckt '+TOP+' ', 1)
    after = after.replace('.ends '+source.TOP+'\n', '.ends '+TOP+'\n', 1)
    result = bank.replace(before, after, 1)+'\n'+cell
    expected = [w[:-1]+[MODEL] if w == old else w for w in defs[source.TOP][1]]
    if (native.definitions(result)[TOP][1] != expected
            or any(definition(result, n) != definition(bank, n) for n in defs if n != source.TOP)):
        raise ValueError('Non-loaded full-bank calls or component definitions changed')
    ports = defs[source.TOP][0]
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = native.mapped_mos(result, TOP, pins, 'XD')
    old_devices = {d['name']: d for d in previous['devices']}
    new = {d['name']: d for d in devices}
    prefix = 'XD:Xfine_isolate:'
    if (len(old_devices) != 1365 or len(new) != len(devices) or len(new) != 1385
            or sum(n.startswith(prefix) for n in old_devices) != 36
            or sum(n.startswith(prefix) for n in new) != 56
            or any(new.get(n) != d for n, d in old_devices.items() if not n.startswith(prefix))):
        raise ValueError('Full-bank retained native terminal maps or exact MOS census changed')
    if len(previous['controls']) != 86 or len(previous['programming_gates']) != 173:
        raise ValueError('Incomplete original full-bank controls')
    if any(new[g['device']]['terminals'][1] != g['gate_node'] for g in previous['programming_gates']):
        raise ValueError('Actual full-bank programming-gate map changed')
    _, leaves = source.source.inventory.native_leaves(source.collapse(result), TOP)
    if sum('fet_' in d['model'] for d in leaves) != 1385 or sum('cap_mim' in d['model'] for d in leaves) != 34:
        raise ValueError('Require full native 1385-MOS/34-MIM bank')
    return result, dict(devices=devices, controls=previous['controls'], programming_gates=previous['programming_gates'])


def fixture(out, identity, spec):
    text = source.fixture(out, identity, spec)
    if text.count(source.TOP) != 1:
        raise ValueError('Original two-stage full-bank fixture changed')
    return text.replace(source.TOP, TOP, 1).replace('OpenLVDS '+source.VERSION, 'OpenLVDS '+VERSION, 1)


def passed_recovery(parent, evidence):
    manifest = recovery.bound(parent)
    identity = manifest['identity']
    report = json.loads((evidence/'summary.json').read_text())
    row = json.loads((parent/'0/summary.json').read_text())
    required = ('input_timing_stimulus_passed', 'full_swing_pulses_passed', 'unwrapped_native_epoch_passed',
                'pulse_order_and_widths_passed', 'current_downstream_250ps_slew_domain_passed',
                'period_screen_passed', 'repeated_delay_screen_passed', 'terminal_screen_passed', 'control_settling_passed')
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', cases=1, errors=0, qualified_phy=False)
            or row['task'] != manifest['tasks'][0] or row['error'] is not None
            or report.get('case') != str((parent/'0').relative_to(ROOT)) or report.get('native_mos') != 433
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('independent_prepared_and_native_source_replay_bound') is not True
            or report.get('all_eight_startup_events_retained') is not True
            or report.get('parameters_changed') is not False
            or any(row['result'].get(k) is not True for k in required)
            or report['recorded_gates'] != {k: v for k, v in row['result'].items() if k.endswith('_passed')}
            or any(sha(ROOT/n) != h for n, h in report['inputs'].items())
            or any(sha(parent/'0'/n) != h for n, h in row['files'].items())
            or recovery.measure(parent/'0', identity) != row['result']):
        raise ValueError('Require complete independently reproduced passing P40 native recovery')
    paths = [evidence/'summary.json', *[ROOT/n for n in report['inputs']],
             *[parent/n for n in ('manifest.json', 'summary.json', 'state.json')], *[ROOT/n for n in identity['inputs']]]
    return identity, paths


def prepare(parent, intervention, evidence):
    manifest = source.bound(parent)
    previous = manifest['identity']
    report = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', cases=4, errors=0, qualified_phy=False)
            or report['comparison'] != source.compare(report['rows'])
            or report['comparison']['component_hypothesis_passed'] is not False):
        raise ValueError('Require complete retained original two-stage latency/history/range evidence')
    ri, paths = passed_recovery(intervention, evidence)
    cell, material_paths, material = recovery.materials(ROOT/ri['materials'])
    paths += material_paths
    if sha(parent/'bank.spice') != manifest['bank_sha256']:
        raise ValueError('Original full native bank changed')
    bank, observations = transform((parent/'bank.spice').read_text(), previous['observations'], cell)
    paths += [parent/n for n in ('manifest.json', 'summary.json', 'state.json', 'bank.spice')]
    paths += [ROOT/n for n in previous['inputs']]
    for task, row in zip(manifest['tasks'], report['rows']):
        folder = parent/task['id']
        if row != json.loads((folder/'summary.json').read_text()) or row['task'] != task:
            raise ValueError('Retained four-point native result changed')
        for name, digest in row['files'].items():
            if sha(folder/name) != digest:
                raise ValueError('Retained original native trace changed')
        paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
        intervention=str(intervention.relative_to(ROOT)), recovery_evidence=str(evidence.relative_to(ROOT)),
        specs=specifications(), inputs=inputs, guards=source.guard_inputs(inputs), observations=observations,
        external_files={**previous['external_files'], **material['external_files']},
        native_revision=dict(native_mos=1385, native_mims=34, non_loaded_native_maps_preserved=1329,
                             programming_gates=173, all_unrelated_calls_and_definitions_preserved=True),
        max_workers=2, priority=1, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'bank.spice').write_text(bank)
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out/str(k)
        folder.mkdir()
        (folder/'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json', dict(identity=identity, tasks=tasks, bank_sha256=sha(out/'bank.spice'), qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out/'manifest.json').read_text())
    identity = manifest['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['scope'] != SCOPE or identity['specs'] != specifications()
            or (identity['max_workers'], identity['priority']) != (2, 1)
            or identity['guards'] != source.guard_inputs(identity['inputs'])
            or any(sha(ROOT/n) != h for n, h in (identity['inputs'] if full else identity['guards']).items())
            or any(sha(Path(n)) != h for n, h in {**identity['pdk_files'], **identity['external_files']}.items())
            or engine() != 'ngspice' or provenance() != identity['simulator']
            or sha(out/'bank.spice') != manifest['bank_sha256']):
        raise ValueError('Full-bank P40 native context changed')
    original = ROOT/identity['parent']
    old = json.loads((original/'manifest.json').read_text())['identity']
    text = (out/'bank.spice').read_text()
    cell = source.source.cell_definition(text, MODEL)
    expected, observations = transform((original/'bank.spice').read_text(), old['observations'], cell)
    if text != expected or observations != identity['observations']:
        raise ValueError('P40 full-bank intervention or complete native observations changed')
    tasks = []
    for k, spec in enumerate(specifications()):
        path = out/str(k)/'bench.cir'
        if path.read_text() != fixture(out, identity, spec):
            raise ValueError('Original native full-bank clock/load/probe fixture changed')
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(path)))
    if manifest['tasks'] != tasks:
        raise ValueError('Require exact original zero/duty/coarse four-point coverage')
    return manifest


def measure(folder, identity, spec):
    return dict(source.measure(folder, identity, spec), scope=SCOPE, qualified_phy=False)


def compare(rows):
    if len(rows) != 4 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['spec'] for r in rows] != specifications():
        raise ValueError('Require complete actual P40 full-bank four-point coverage')
    original = [dict(row, spec=source.specifications()[k]) for k, row in enumerate(rows)]
    return source.compare(original)


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior or partial full-bank P40 native execution')
        atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']
            result = error = None
            try:
                with lease(ROOT, priority=1, label=CONTEXT+'_'+task['id']):
                    bound(out, full=False)
                    process = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr)
                process.check_returncode()
                result = measure(folder, identity, task['spec'])
            except Exception as exception:
                error = str(exception)
            row = dict(task=task, spec=task['spec'], result=result, error=error,
                files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, manifest['tasks']))
        bound(out)
        atomic(out/'summary.json', dict(rows=rows, comparison=compare(rows), qualified_phy=False, scope=SCOPE))
        atomic(out/'state.json', dict(status='complete', cases=4, errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    prepare_parser = actions.add_parser('prepare')
    for key in ('parent', 'intervention', 'evidence'):
        prepare_parser.add_argument(key, type=Path)
    actions.add_parser('run').add_argument('artifact', type=Path)
    args = parser.parse_args()
    print(prepare(args.parent.resolve(), args.intervention.resolve(), args.evidence.resolve())
          if args.action == 'prepare' else run(args.artifact.resolve()), flush=True)
