#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate first-buffer fanout after the stronger taper's measured SS failure."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

import driver_stage0_balance as circuit
import qualify_stronger_driver_shape as stronger
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT = Path(__file__).resolve().parents[1]
CASES = ['ss_25_negative_op', 'ff_40_negative_op']
sha = stronger.sha


def prepare(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/driver_shape_source'):
        raise ValueError('Use the stronger source matrix')
    stronger.check_variant(parent)
    m = stronger.pilot.bound(parent)
    paths = [parent / 'manifest.json']
    reference = {}
    sources = []
    for name in CASES:
        task = next(t for t in m['tasks'] if t['id'] == name)
        row, files = stronger.pilot.completed(parent, task, stronger.pilot.VARIANT)
        reference[name] = row['metrics']
        paths += files
        sources.append((parent / name / 'source.spice').read_text())
    if reference[CASES[0]]['common_mode_pp_v'] <= .150 or reference[CASES[1]]['common_mode_pp_v'] > .150:
        raise ValueError('Require actual SS common-mode failure and passing FF common-mode control')
    if sources[0] != sources[1]:
        raise ValueError('Parent corners use different circuits')
    inputs = dict(m['identity']['inputs'])
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(m['identity']['code'])
    for name in [Path(__file__).name, 'driver_stage0_balance.py', 'qualify_stronger_driver_shape.py']:
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs, code=code,
        simulator=provenance(), reference_metrics=reference,
        scope='Two causal source controls, SS25 and FF40, same negative initial state '
              'and original complete 80 ns/1 ps alternating stimulus. Only first '
              'buffer parallel count changes 1 to 2 in both branches: 2/4/8 taper. '
              'Original 30 um capacitors, later stages, mirror, bridge, CMFB, rails, '
              'bias and load remain. Common-mode/DC/edge-count control only, without '
              'fresh positive DC calibration, full transition or PVT qualification.')
    out = ROOT / 'build/diagnostics/driver_stage0_balance' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    source = circuit.transform(sources[0])
    tasks = []
    for name in CASES:
        old, folder = parent / name, out / name
        folder.mkdir(exist_ok=True)
        deck = (old / 'bench.cir').read_text()
        include = f'.include "{old}/source.spice"'
        if deck.count(include) != 1:
            raise ValueError('Unexpected parent source include')
        deck = deck.replace(include, f'.include "{folder}/source.spice"')
        for filename, body in [('source.spice', source), ('bench.cir', deck)]:
            p = folder / filename
            if p.exists() and p.read_text() != body:
                raise ValueError('Prepared first-buffer control changed')
            if not p.exists():
                p.write_text(body)
        tasks.append(dict(id=name, files={n: sha(folder / n) for n in ['source.spice', 'bench.cir']}))
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics/driver_stage0_balance'):
        raise ValueError('Use prepared first-buffer control')
    m = stronger.pilot.bound(out)
    stamp = sha(out / 'manifest.json')
    req = json.loads((ROOT / 'requirements.json').read_text())

    def unchanged():
        stronger.pilot.bound(out)
        if sha(out / 'manifest.json') != stamp or any(sha(out / t['id'] / n) != h
                for t in m['tasks'] for n, h in t['files'].items()):
            raise ValueError('First-buffer control context changed')

    if [t['id'] for t in m['tasks']] != CASES:
        raise ValueError('Require both declared causal controls')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists()
                for t in m['tasks'] for n in ['bench.raw', 'ngspice.log', 'summary.json']):
            raise ValueError('Prior or partial first-buffer output retained')
        atomic(out / 'state.json', dict(status='running_controls', qualified_phy=False))

        def execute(task):
            folder = out / task['id']
            atomic(folder / 'state.json', dict(status='waiting_for_slot'))
            with lease(ROOT, priority=2, label='stage0_' + task['id']):
                unchanged()
                atomic(folder / 'state.json', dict(status='running'))
                p = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                    cwd=folder, capture_output=True, text=True)
            (folder / 'console.log').write_text(p.stdout + p.stderr)
            unchanged()
            metrics = circuit.measure(folder) if p.returncode == 0 else None
            dc = stronger.matrix.shape.initial_dc(*stronger.matrix.shape.read_wave(folder / 'bench.cir.prn')) if metrics else None
            passed = bool(metrics and metrics['common_mode_pp_v'] <= .150 and metrics['rising_output_edges'] == 22 and
                req['tx_differential_min_v'] <= abs(dc['differential_v']) <= req['tx_differential_max_v'] and
                req['tx_common_mode_min_v'] <= dc['common_mode_v'] <= req['tx_common_mode_max_v'] and
                max(dc['differential_pp_v'], dc['common_mode_pp_v']) <= 1e-4)
            row = dict(case=task['id'], returncode=p.returncode, control_passed=passed,
                metrics=metrics, initial_dc=dc, reference_metrics=m['identity']['reference_metrics'][task['id']],
                manifest_sha256=stamp, qualified_phy=False,
                files={n: sha(folder / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'] if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            atomic(folder / 'state.json', dict(status='completed' if metrics else 'held_numerical_failure'))
            return row

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, m['tasks']))
        unchanged()
        passed = all(r['control_passed'] for r in results)
        capture_manifest(out / 'summary.json', dict(results=results, controls_passed=passed,
            manifest_sha256=stamp, qualified_phy=False, scope=m['identity']['scope']))
        atomic(out / 'state.json', dict(status='completed_controls' if passed else 'held_control_failure', qualified_phy=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
