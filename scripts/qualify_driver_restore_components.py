#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check a matched driver variant in the original thirty source/native fixtures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic
from dll_measurements import read_wave
from driver_restore_variant import TOP
import probe_native_driver_restore as native
from reduce_rc import number
from spice_engine import command, engine, provenance
from spice_library import checked_netlist, library
from spice_probes import ProbeNetwork
from spice_slots import slot
from stage_phy_candidate import overlay
from verify_analog import driver_metrics, driver_dc_metrics
from verify_component_evidence import check_case

ROOT = Path(__file__).resolve().parents[1]
CODE = ['qualify_driver_restore_components.py', 'verify_analog.py', 'verify_component_evidence.py',
        'evidence_scope.py', 'dll_campaign.py', 'dll_measurements.py', 'reduce_rc.py',
        'spice_engine.py', 'spice_library.py', 'spice_slots.py', 'spice_probes.py',
        'spice_scope.py', 'stage_phy_candidate.py', 'run_ngspice.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(requirements):
    result = list(itertools.product(['schematic', 'native'], requirements['process_corners'],
                                    requirements['temperatures_c']))
    if len(result) != len(set(result)):
        raise ValueError('Duplicate driver qualification conditions')
    return result


def check_coverage(tasks, requirements):
    actual = [(t['view'], t['process'], t['temperature']) for t in tasks]
    if len(actual) != len(cases(requirements)) or set(actual) != set(cases(requirements)):
        raise ValueError('Incomplete or duplicate driver component coverage')
    if any(t['id'] != f"{t['view']}_driver_{t['process']}_{t['temperature']}" for t in tasks):
        raise ValueError('Driver component case name differs from condition')


def fixture(old, folder, model, view):
    body = overlay((old / 'source.spice').read_text(), model, TOP, ('lvds_bias',))
    deck = (old / 'bench.cir').read_text()
    include = f'.include "{old}/source.spice"'
    if deck.count(include) != 1:
        raise ValueError('Expected one captured component source inclusion')
    deck = deck.replace(include, f'.include "{folder}/source.spice"')
    if view == 'native':
        for leaf in ['SINK', 'TOP', 'DP', 'DN']:
            # Require the named bus alias; do not pick an arbitrary RC terminal.
            node = TOP + '__' + leaf
            if not re.search(r'\b' + re.escape(node) + r'\b', model):
                raise ValueError('Missing native driver observation alias ' + leaf)
            deck = re.sub(r'XD:XCORE:' + re.escape(node) + r'(?:\.t\d+)?\b',
                          'XD:XCORE:' + node, deck)
    prints = re.findall(r'(?im)^\.print tran[^\n]*', deck)
    transients = re.findall(r'(?im)^\.tran[^\n]*', deck)
    if len(prints) != 1 or len(transients) != 1:
        raise ValueError('Expected the original component print and transient commands')
    ProbeNetwork(body).validate(deck, re.findall(r'V\(([^)]+)\)', prints[0], re.I))
    return body, deck, number(transients[0].split()[2])


def native_ready(root):
    """Never call a producer that could launch a missing native simulation."""
    report = root / 'summary.json'
    if not report.exists() or any(not (root / case / 'summary.json').exists() for case in native.CASES):
        raise ValueError('Both matched native driver cases must complete first')
    summary = json.loads(report.read_text())
    if (not summary.get('diagnostic_complete') or len(summary.get('results', [])) != 2 or
            {r['task'] for r in summary['results']} != set(native.CASES)):
        raise ValueError('Incomplete matched native driver coverage')
    # The original producer verifies circuit/runtime/model hashes, complete
    # finite monotonic traces and every cached measurement before admission.
    native.run(root)


def prepare(comparison, variant):
    if engine() != 'ngspice' or not comparison.is_relative_to(ROOT / 'build/diagnostics/driver_native_restore'):
        raise ValueError('Use an isolated matched native driver comparison')
    capture = json.loads((comparison / 'manifest.json').read_text())
    context = capture['identity']
    models, physical_files, physical_code = native.physical_models(
        {case: ROOT / path for case, path in context['layouts'].items()})
    layout = ROOT / context['layouts'][variant]
    for name, stamp in context['code'].items():
        if digest(ROOT / 'scripts' / name) != stamp:
            raise ValueError('Matched native driver producer changed')
    if provenance() != context['simulator_provenance']:
        raise ValueError('Matched native driver runtime changed')
    for name, stamp in context['inputs'].items():
        if digest(ROOT / name) != stamp:
            raise ValueError('Matched native driver input changed')
    names = set(CODE) | set(context['code']) | set(physical_code)
    paths = physical_files + [comparison / 'manifest.json', ROOT / 'requirements.json',
                              ROOT / 'analog/openlvds.spice', ROOT / 'build/extracted/current.json',
                              ROOT / 'build/layout/current.json']
    paths += [ROOT / name for name in context['inputs']]
    req = json.loads((ROOT / 'requirements.json').read_text())
    source = (ROOT / 'analog/openlvds.spice').read_bytes()
    baseline, inputs, _ = library(extracted=True, designs={TOP, 'lvds_bias'})
    fixtures = []
    for view, corner, temp in cases(req):
        old = ROOT / 'build' / ('analog' if view == 'schematic' else 'analog_extracted') / f'driver_{corner}_{temp}'
        proof = check_case(old, 'driver', source if view == 'schematic' else baseline,
                           {} if view == 'schematic' else inputs, digest(ROOT / 'scripts/verify_analog.py'),
                           digest(ROOT / 'requirements.json'), engine(), provenance())
        if not proof['passed']:
            raise ValueError('Original driver fixture is stale or failed: ' + str(old))
        paths += [old / n for n in ['bench.cir', 'source.spice', 'summary.json', 'bench.cir.prn', 'runner.py']]
        fixtures.append((view, corner, temp, old))
    identity = dict(comparison=str(comparison.relative_to(ROOT)), variant=variant,
                    layout=str(layout.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
                    code={n: digest(ROOT / 'scripts' / n) for n in names},
                    simulator_provenance=provenance())
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root = ROOT / 'build/diagnostics/driver_components' / fingerprint
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.preparation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'manifest.json').exists():
            if json.loads((root / 'manifest.json').read_text())['identity'] != identity:
                raise ValueError('Driver component preparation identity changed')
            return root
        tasks = []
        for view, corner, temp, old in fixtures:
            name = f'{view}_driver_{corner}_{temp}'
            folder = root / name
            folder.mkdir(exist_ok=True)
            model = (layout / 'candidate.spice').read_text() if view == 'schematic' else models[variant]
            body, deck, stop = fixture(old, folder, model, view)
            (folder / 'source.spice').write_text(body)
            (folder / 'bench.cir').write_text(deck)
            tasks.append(dict(id=name, view=view, process=corner, temperature=temp, stop_seconds=stop,
                              files={n: digest(folder / n) for n in ['source.spice', 'bench.cir']}))
        atomic(root / 'manifest.json', dict(identity=identity, tasks=tasks, required=len(tasks), qualified_phy=False))
    return root


def measurements(wave, headers, stop):
    if (wave.ndim != 2 or wave.shape[1] < 9 or len(wave) < 2 or
            any(headers.get(name) != i for i, name in [(1, 'TIME'), (2, 'V(D)'), (3, 'V(P)'), (4, 'V(N)')]) or
            not np.isfinite(wave).all() or wave[0, 1] > 1e-15 or
            wave[-1, 1] < stop - 1e-12 or np.any(np.diff(wave[:, 1]) <= 0)):
        raise ValueError('Incomplete or invalid driver component waveform')
    result = driver_metrics(wave)
    result['loaded_eye_passed'] = result['passed']
    result['dc_output'] = driver_dc_metrics(wave)
    result['passed'] = result['passed'] and result['dc_output']['passed']
    return result


def run(root, jobs):
    if not root.is_relative_to(ROOT / 'build/diagnostics/driver_components'):
        raise ValueError('Use an isolated prepared driver component campaign')
    manifest = json.loads((root / 'manifest.json').read_text())
    manifest_sha = digest(root / 'manifest.json')
    identity = manifest['identity']
    def unchanged():
        if digest(root / 'manifest.json') != manifest_sha:
            raise ValueError('Driver component manifest changed')
        if provenance() != identity['simulator_provenance'] or any(
                digest(ROOT / 'scripts' / n) != h for n, h in identity['code'].items()):
            raise ValueError('Driver component producer changed')
        if any(digest(ROOT / n) != h for n, h in identity['inputs'].items()):
            raise ValueError('Driver component input changed')
        if root.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]:
            raise ValueError('Driver component identity changed')
    def task_unchanged(task):
        if any(digest(root / task['id'] / n) != h for n, h in task['files'].items()):
            raise ValueError('Driver component fixture changed')
    def execute(task):
        task_unchanged(task)
        folder = root / task['id']
        path = folder / 'summary.json'
        cached = json.loads(path.read_text()) if path.exists() else None
        if cached is not None:
            if digest(folder / 'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Driver component waveform changed')
        else:
            atomic(folder / 'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with slot():
                unchanged()
                task_unchanged(task)
                atomic(folder / 'execution.json', dict(status='running', qualified_phy=False))
                process = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                         cwd=folder, capture_output=True, text=True)
            (folder / 'console.log').write_text(process.stdout + process.stderr)
            process.check_returncode()
        task_unchanged(task)
        wave, headers = read_wave(folder / 'bench.cir.prn')
        result = dict(task=task['id'], **measurements(wave, headers, task['stop_seconds']), qualified_phy=False,
                      manifest_sha256=digest(root / 'manifest.json'), waveform_sha256=digest(folder / 'bench.cir.prn'),
                      deck_sha256=task['files']['bench.cir'])
        if cached is not None and cached != result:
            raise ValueError('Driver component cached analysis differs from waveform')
        atomic(path, result)
        atomic(folder / 'execution.json', dict(status='completed', passed=result['passed'], qualified_phy=False))
        return result
    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        check_coverage(manifest['tasks'], json.loads((ROOT / 'requirements.json').read_text()))
        layout = ROOT / identity['layout']
        info = json.loads((layout / 'extraction.json').read_text())
        for task in manifest['tasks']:
            old = ROOT / 'build' / ('analog' if task['view'] == 'schematic' else 'analog_extracted') / f"driver_{task['process']}_{task['temperature']}"
            folder = root / task['id']
            if any(digest(folder / n) != h for n, h in task['files'].items()):
                raise ValueError('Driver component fixture changed')
            model = (layout / 'candidate.spice').read_text() if task['view'] == 'schematic' else checked_netlist(info)
            body, deck, stop = fixture(old, folder, model, task['view'])
            if (body != (folder / 'source.spice').read_text() or deck != (folder / 'bench.cir').read_text()
                    or stop != task['stop_seconds']):
                raise ValueError('Driver component differs from original fixture or selected model')
        native_ready(ROOT / identity['comparison'])
        def safe(task):
            try:
                return execute(task)
            except Exception as error:
                atomic(root / task['id'] / 'execution.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
                return dict(task=task['id'], passed=False, error=str(error), qualified_phy=False)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(safe, manifest['tasks']))
        unchanged()
        for task in manifest['tasks']:
            task_unchanged(task)
        atomic(root / 'summary.json', dict(passed=all(r['passed'] for r in results), required=len(manifest['tasks']),
            passed_cases=sum(r['passed'] for r in results), results=results, qualified_phy=False,
            manifest_sha256=digest(root / 'manifest.json'),
            scope='Selected driver source/native component DC, polarity, cadence and loaded eye only; no PHY release qualification'))
    print(root / 'summary.json', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--variant', choices=native.CASES, default='restore_64_24')
    parser.add_argument('--jobs', type=int, choices=range(1, 7), default=3)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve(), args.variant), flush=True)
    else:
        run(args.artifact.resolve(), args.jobs)
