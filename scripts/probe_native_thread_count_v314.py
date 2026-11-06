#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay full native endpoints with explicit thread counts; no backend adoption."""
import argparse
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_regular_regenerated_bank_v263 as source
import run_native_threaded_binary_v313 as runner
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
sha = source.sha
VERSION = 'full-native-endpoint-explicit-thread-parity-and-contended-runtime-v314.1'
CONTEXT = 'native_thread_count_v314'
TIMING_TOLERANCE_PS = .1
VOLTAGE_TOLERANCE_V = .001
SCOPE = ('Full unchanged native SS40/410 MHz fine31 endpoints and paired 40% thread-control '
         'experiment; exact original circuit/PDK/KLU/tolerances/25ns stimulus, no backend, '
         'routed bank, PVT, clock or PHY admission')


def plan():
    return [('1', 1), ('2', 1), ('2', 2)]


def references(parent, manifest):
    rows = {}
    paths = []
    for case_id in ('1', '2'):
        folder = parent / case_id
        row = json.loads((folder / 'summary.json').read_text())
        if (row['task'] != manifest['tasks'][int(case_id)]
                or row['spec'] != source.specifications()[int(case_id)]
                or row['error'] is not None or row['result'] is None
                or row['result']['current_clock_interface_screen_passed'] is not True
                or not {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'} <= set(row['files'])
                or any(sha(folder / n) != h for n, h in row['files'].items())):
            raise ValueError('Require complete passing unchanged original duty endpoints')
        if source.measure(folder, manifest['identity'], row['spec']) != row['result']:
            raise ValueError('Original full native endpoint metrics do not reproduce')
        elapsed = re.findall(r'Total elapsed time \(seconds\)\s*=\s*(\S+)',
                             (folder / 'ngspice.log').read_text())
        if len(elapsed) != 1 or not math.isfinite(float(elapsed[0])) or float(elapsed[0]) <= 0:
            raise ValueError('Missing original historical elapsed-time accounting')
        rows[case_id] = dict(row=row, historical_ngspice_elapsed_seconds=float(elapsed[0]))
        paths += [folder / 'summary.json', *[folder / n for n in row['files']]]
    return rows, paths


def prepare(parent):
    manifest = source.bound(parent)
    previous = manifest['identity']
    refs, paths = references(parent, manifest)
    if engine() != 'ngspice' or provenance() != previous['simulator']:
        raise ValueError('Require original pinned ngspice environment')
    paths += [parent / 'manifest.json', parent / 'bank.spice']
    paths += [ROOT / n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT / 'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    guards = {n: h for n, h in inputs.items() if Path(n).suffix in ('.py', '.json', '.spice', '.cir', '.sh')}
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
                    references=refs, plan=plan(), inputs=inputs, guarded_inputs=guards,
                    timing_tolerance_ps=TIMING_TOLERANCE_PS, voltage_tolerance_v=VOLTAGE_TOLERANCE_V,
                    max_workers=1, priority=2, scope=SCOPE)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / 'build/diagnostics' / CONTEXT / digest
    out.mkdir(parents=True, exist_ok=False)
    tasks = []
    for k, (case_id, threads) in enumerate(plan()):
        folder = out / str(k)
        folder.mkdir()
        (folder / 'bench.cir').write_bytes((parent / case_id / 'bench.cir').read_bytes())
        tasks.append(dict(id=str(k), source_id=case_id, threads=threads,
                          spec=refs[case_id]['row']['spec'], deck_sha256=sha(folder / 'bench.cir')))
    atomic(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out / 'manifest.json').read_text())
    identity = manifest['identity']
    if (out.parent != ROOT / 'build/diagnostics' / CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['plan'] != [list(p) for p in plan()]
            or identity['max_workers'] != 1 or identity['priority'] != 2
            or identity['timing_tolerance_ps'] != TIMING_TOLERANCE_PS
            or identity['voltage_tolerance_v'] != VOLTAGE_TOLERANCE_V
            or identity['guarded_inputs'] != {n: h for n, h in identity['inputs'].items()
                                             if Path(n).suffix in ('.py', '.json', '.spice', '.cir', '.sh')}
            or engine() != 'ngspice' or provenance() != identity['simulator']
            or any(sha(ROOT / n) != h for n, h in (identity['inputs'] if full else identity['guarded_inputs']).items())
            or any(sha(Path(n)) != h for n, h in {**identity['pdk_files'], **identity['external_files']}.items())
            or len(manifest['tasks']) != 3):
        raise ValueError('Explicit-thread native experiment inputs changed')
    for k, (case_id, threads) in enumerate(plan()):
        path = out / str(k) / 'bench.cir'
        expected = dict(id=str(k), source_id=case_id, threads=threads,
                        spec=identity['references'][case_id]['row']['spec'], deck_sha256=sha(path))
        if (manifest['tasks'][k] != expected
                or path.read_bytes() != (ROOT / identity['parent'] / case_id / 'bench.cir').read_bytes()):
            raise ValueError('Original full native stimulus changed')
    return manifest


def vector_difference(actual, reference):
    try:
        a = np.asarray(actual, dtype=float)
        b = np.asarray(reference, dtype=float)
    except (TypeError, ValueError):
        return None
    if (a.ndim != 1 or b.ndim != 1 or len(a) != len(b) or not len(a)
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        return None
    return float(np.max(np.abs(a-b)))


def record_difference(actual, reference, field):
    if len(actual) != len(reference):
        return None
    for a, b in zip(actual, reference):
        if {k: v for k, v in a.items() if k != field} != {k: v for k, v in b.items() if k != field}:
            return None
    return vector_difference([a[field] for a in actual], [b[field] for b in reference])


def parity(actual, reference):
    gates = {k: v for k, v in reference.items() if k.endswith('_passed')}
    timing = []
    for field in ('edge_delays_ps', 'output_slews_10_90_ps'):
        for edge in ('rise', 'fall'):
            a, b = actual.get(field, {}).get(edge, []), reference[field][edge]
            timing.append(vector_difference(a, b) if len(a) == len(b) == 8 else None)
    timing.append(vector_difference([actual['maximum_period_error_ps']], [reference['maximum_period_error_ps']]))
    terminal = record_difference(actual['terminal_stress'], reference['terminal_stress'], 'maximum_terminal_difference_v')
    controls = [record_difference(actual[n], reference[n], 'maximum_deviation_v')
                for n in ('controls', 'programming_gates')]
    gate_match = all(actual.get(k) == v for k, v in gates.items())
    timed = all(v is not None and v <= TIMING_TOLERANCE_PS for v in timing)
    voltage = all(v is not None and v <= VOLTAGE_TOLERANCE_V for v in [terminal, *controls])
    return dict(original_native_gates_reproduced=gate_match,
                original_native_interface_passed=actual.get('current_clock_interface_screen_passed') is True,
                maximum_timing_difference_ps=max(timing) if all(v is not None for v in timing) else None,
                maximum_terminal_peak_difference_v=terminal,
                maximum_control_deviation_difference_v=max(controls) if all(v is not None for v in controls) else None,
                metric_parity_passed=bool(gate_match and timed and voltage
                                         and actual.get('current_clock_interface_screen_passed') is True))


def compare(rows):
    if len(rows) != 3 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [(r['task']['source_id'], r['task']['threads']) for r in rows] != plan():
        raise ValueError('Require both single-thread duty endpoints and the paired two-thread control')
    runtimes = [r['runtime'] for r in rows]
    walls = [r['wall_seconds'] for r in runtimes]
    if any(not math.isfinite(v) or v <= 0 for v in walls):
        raise ValueError('Require finite positive measured wall times')
    parity_passed = all(r['parity']['metric_parity_passed'] for r in rows)
    threads_verified = all(r['active_thread_configuration_observed'] and r['native_transient_validated']
                           and r['configured_threads'] == row['task']['threads']
                           for row, r in zip(rows, runtimes))
    return dict(complete_three_case_experiment=True, full_native_metric_parity_passed=parity_passed,
                configured_thread_counts_observed=threads_verified,
                paired_40_percent_two_over_one_wall_ratio=walls[2]/walls[1],
                single_thread_faster_on_paired_case=bool(parity_passed and threads_verified and walls[1] < walls[2]),
                backend_admitted=False, electrical_qualification_passed=False, qualified_phy=False,
                scope='Sequential full native cases on a shared busy machine; measured paired-case ratio only, no universal speedup or automatic backend adoption')


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists():
            raise ValueError('Retain previous or partial explicit-thread experiment')
        atomic(out / 'state.json', dict(status='running', qualified_phy=False))
        rows = []
        try:
            for task in manifest['tasks']:
                folder = out / task['id']
                result = error = runtime = comparison = None
                try:
                    with lease(ROOT, priority=2, label=CONTEXT + '_' + task['id']):
                        bound(out, full=False)
                        process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_native_threaded_binary_v313.py'),
                            '--threads', str(task['threads']), '-l', str(folder / 'ngspice.log'), str(folder / 'bench.cir')],
                            capture_output=True, text=True)
                    (folder / 'console.log').write_text(process.stdout + process.stderr)
                    process.check_returncode()
                    runtime = json.loads((folder / 'runtime.json').read_text())
                    result = source.measure(folder, identity, task['spec'])
                    comparison = parity(result, identity['references'][task['source_id']]['row']['result'])
                except Exception as exception:
                    error = str(exception)
                row = dict(task=task, result=result, runtime=runtime, parity=comparison, error=error,
                           files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
                atomic(folder / 'summary.json', row)
                rows.append(row)
            bound(out)
            atomic(out / 'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE,
                                              backend_admitted=False, qualified_phy=False))
            atomic(out / 'state.json', dict(status='complete', cases=3,
                                           errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
        except Exception as exception:
            atomic(out / 'state.json', dict(status='failed', error=str(exception), qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.action in ('prepare', 'campaign'):
        artifact = prepare(artifact)
        print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
