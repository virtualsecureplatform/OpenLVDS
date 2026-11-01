#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run retained baseline and PMOS p8/t4 source-clock controls after fifteen DC passes."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import receiver_architecture_matrix as matrix
import receiver_architecture_observations as observed
import receiver_clamp_experiment as engine
import receiver_decision_load_clock as clock

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
VARIANT = 'pmos_p8_t4'
sha = observed.experiment.digest


def static_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_matrix'):
        raise ValueError('Use the PMOS architecture DC matrix')
    manifest = json.loads((screen/'manifest.json').read_text()); children = manifest['identity']['children']
    if manifest['identity']['variant'] != VARIANT:
        raise ValueError('This source-clock producer is specific to PMOS p8/t4')
    if (len(children) != 15 or not (screen/'summary.json').is_file() or
        any(not (ROOT/c['root']/'summary.json').is_file() for c in children)):
        raise ValueError('Complete all fifteen PMOS DC cases before source clocks')
    with (screen/'.clock_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX); report = matrix.run(screen)
    if report.get('required') != 15 or report.get('dc_all_passed') is not True:
        raise ValueError('PMOS source DC/current/stress matrix must pass every original case')
    paths = [screen/'manifest.json', screen/'summary.json']
    for child in children:
        folder = ROOT/child['root']
        paths.extend(folder/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn'])
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def source_variant(source, modified=True):
    # False is deliberately the retained original reduced-tail reference.
    # Only the two clamped-labelled interventions use the PMOS alternative;
    # these fixture labels are historical and do not imply restored clamps.
    return observed.experiment.source_variant(source, modified, VARIANT)


@contextmanager
def profile():
    previous = clock.factory, clock.static_gate, engine.source_variant
    try:
        clock.factory = SimpleNamespace(source_variant=source_variant, experiment=engine)
        clock.static_gate = static_gate; engine.source_variant = source_variant
        yield
    finally:
        clock.factory, clock.static_gate, engine.source_variant = previous


def prepare(parent, screen):
    proofs = static_gate(screen)
    inherited = {n for path in proofs if path.endswith('/manifest.json')
        for n in json.loads((ROOT/path).read_text())['identity'].get('code', {})}
    previous = engine.CODE
    try:
        engine.CODE = sorted(set(engine.CODE) | set(observed.experiment.CODE) | inherited | {
            NAME, 'receiver_architecture_observations.py', 'receiver_architecture_matrix.py',
            'receiver_decision_load_clock.py', 'receiver_decision_load_matrix.py', 'receiver_tail_timestep_retry.py'})
        with profile():
            base = engine.prepare(parent)
    finally:
        engine.CODE = previous
    return clock.derive(base, screen, proofs)


def run(root, wait_slot=None):
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != sha(Path(__file__)):
        raise ValueError('PMOS source-clock producer changed')
    with profile():
        clock.run(root, wait_slot)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--dc-matrix', type=Path)
    p.add_argument('--wait-slot', type=int, choices=range(6)); a = p.parse_args()
    if a.action == 'prepare':
        if a.dc_matrix is None:
            p.error('--dc-matrix is required')
        print(prepare(a.artifact.resolve(), a.dc_matrix.resolve()), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
