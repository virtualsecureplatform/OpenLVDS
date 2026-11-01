#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen each admitted passive bias correction with the original source clocks."""
import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import matrix_receiver_common_mode as matrix
import receiver_common_mode as dc
import receiver_lvt_pair_experiment as original
import receiver_lvt_pair_clock as original_clock
import receiver_clamp_experiment as engine
import receiver_decision_load_clock as clock
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
VARIANTS = ['reference_return', 'rail_pullup']


def source_variant(source, modified, variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared passive common-mode correction')
    base = original.source_variant(source, modified)
    return dc.transform(base, variant) if modified else base


def static_gate(screen, variant):
    if variant not in VARIANTS or not screen.is_relative_to(ROOT/'build/diagnostics/receiver_common_mode_matrix'):
        raise ValueError('Use the passive common-mode DC matrix and a declared correction')
    manifest = json.loads((screen/'manifest.json').read_text())
    children = manifest['identity']['children']
    matrix.coverage(children, json.loads((ROOT/'requirements.json').read_text()))
    if not (screen/'summary.json').is_file() or any(
            not (ROOT/c['root']/n).is_file() for c in children
            for n in ['summary.json']+[v+'/summary.json' for v in dc.VARIANTS]):
        raise ValueError('Complete all fifteen common-mode DC cases before source clocks')
    # No missing child can be launched by this cached remeasurement path.
    with (screen/'.clock_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        report = matrix.run(screen)
    gate = report['variants'][variant]
    if gate != dict(required=15, completed=15, passed_cases=15, source_dc_passed=True):
        raise ValueError('Selected correction must pass all fifteen original DC/current/stress cases')
    paths = [screen/'manifest.json', screen/'summary.json', screen/'source_dc_admission'/(variant+'.json')]
    candidate_hash = manifest['identity']['candidate_sha256'][variant]
    for c in children:
        child = ROOT/c['root']
        paths.extend(child/n for n in ['manifest.json', 'summary.json'])
        for v in ['control', variant]:
            folder = child/v
            paths.extend(folder/n for n in ['candidate.spice', 'source.spice', 'bench.cir', 'bench.cir.prn', 'summary.json'])
        if dc.sha(child/variant/'candidate.spice') != candidate_hash:
            raise ValueError('Selected PVT candidate circuit bytes changed')
    return {str(p.relative_to(ROOT)): dc.sha(p) for p in paths}


def prepare(parent, screen, variant):
    proofs = static_gate(screen, variant)
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the completed original LVT source-clock context')
    previous = json.loads((parent/'manifest.json').read_text())
    if (previous['identity']['code'].get('receiver_lvt_pair_clock.py') != dc.sha(ROOT/'scripts/receiver_lvt_pair_clock.py') or
            not (parent/'source_clock_admission.json').is_file()):
        raise ValueError('Require the original LVT clock producer and completed admission')
    admission = json.loads((parent/'source_clock_admission.json').read_text())
    if (admission.get('source_clock_passed') is not True or
            admission.get('manifest_sha256') != dc.sha(parent/'manifest.json') or
            admission.get('report_sha256') != dc.sha(parent/'summary.json') or
            not clock.admitted(json.loads((parent/'summary.json').read_text()))):
        raise ValueError('Original LVT source-clock admission is changed or failed')
    if len(previous['tasks']) != 3 or {t['id'] for t in previous['tasks']} != clock.CASES:
        raise ValueError('Require all three original clock fixtures')
    if any(not (parent/t['id']/'summary.json').is_file() for t in previous['tasks']):
        raise ValueError('Complete every original LVT source-clock control first')
    original_clock.run(parent)  # All reports exist: cached scientific remeasurement only.
    identity = copy.deepcopy(previous['identity'])
    identity.update(passive_common_mode_variant=variant, static_screen=str(screen.relative_to(ROOT)),
        static_proofs=proofs, scope='Original three full 80 ns, 47-period source-clock controls for the declared passive correction; retained reduced-tail reference, native shared bias and digital RX. No receiver wire RC or physical/native/PHY admission.')
    identity['inputs'].update(proofs)
    for n in ['manifest.json', 'summary.json', 'source_clock_admission.json']:
        identity['inputs'][str((parent/n).relative_to(ROOT))] = dc.sha(parent/n)
    identity['code'].update({n: dc.sha(ROOT/'scripts'/n) for n in
        [NAME, 'matrix_receiver_common_mode.py', 'receiver_common_mode.py']})
    for task in previous['tasks']:
        for n, h in task['files'].items():
            p = parent/task['id']/n
            if dc.sha(p) != h:
                raise ValueError('Original LVT clock fixture changed')
            identity['inputs'][str(p.relative_to(ROOT))] = h
    root = ROOT/'build/diagnostics/receiver_clamp'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    tasks = copy.deepcopy(previous['tasks']); root.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'analog/openlvds.spice').read_text()
    candidate_hash = json.loads((screen/'manifest.json').read_text())['identity']['candidate_sha256'][variant]
    for task in tasks:
        old = parent/task['id']; folder = root/task['id']; folder.mkdir(exist_ok=True)
        if (old/'candidate.spice').read_text() != original.source_variant(source, task['clamped']):
            raise ValueError('Original clock source differs from its declared LVT factory')
        candidate = source_variant(source, task['clamped'], variant)
        if task['clamped'] and hashlib.sha256(candidate.encode()).hexdigest() != candidate_hash:
            raise ValueError('Clock source differs from admitted DC candidate bytes')
        ports, devices = engine.flatten(engine.circuits(candidate), engine.TOP)
        library = engine.replace((old/'library.spice').read_text(), engine.TOP, engine.schematic_text(engine.TOP, ports, devices))
        for protected in ['lvds_bias', 'openlvds_ddr_rx']:
            if engine.closure_hash(library, protected) != engine.closure_hash((old/'library.spice').read_text(), protected):
                raise ValueError('Passive clock correction changed an unrelated closure')
        deck = (old/'bench.cir').read_text(); before = f'.include "{old}/library.spice"'
        if deck.count(before) != 1 or clock.tighten(deck) != deck:
            raise ValueError('Original clock binding or numerical policy changed')
        deck = deck.replace(before, f'.include "{folder}/library.spice"')
        engine.ProbeNetwork(library).validate(deck, task['aliases'].values())
        for n, text in [('candidate.spice', candidate), ('library.spice', library), ('bench.cir', deck)]:
            p = folder/n
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared passive source-clock fixture changed')
            if not p.exists():
                p.write_text(text)
        task['files'] = {n: dc.sha(folder/n) for n in task['files']}
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


@contextmanager
def profile(variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared passive correction')
    previous = clock.factory, clock.static_gate
    try:
        clock.factory = SimpleNamespace(source_variant=lambda s, changed: source_variant(s, changed, variant), experiment=engine)
        clock.static_gate = lambda screen: static_gate(screen, variant)
        yield
    finally:
        clock.factory, clock.static_gate = previous


def run(root, wait_slot=None):
    m = json.loads((root/'manifest.json').read_text())
    if m['identity']['code'].get(NAME) != dc.sha(Path(__file__)):
        raise ValueError('Passive source-clock producer changed')
    with profile(m['identity']['passive_common_mode_variant']):
        clock.run(root, wait_slot)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--dc-matrix', type=Path)
    p.add_argument('--variant', choices=VARIANTS); p.add_argument('--wait-slot', type=int, choices=range(6)); a = p.parse_args()
    if a.action == 'prepare':
        if a.dc_matrix is None or a.variant is None:
            p.error('--dc-matrix and --variant are required')
        print(prepare(a.artifact.resolve(), a.dc_matrix.resolve(), a.variant), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
