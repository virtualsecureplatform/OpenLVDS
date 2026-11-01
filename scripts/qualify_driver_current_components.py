#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the corrected driver with the original thirty source/native fixtures."""
import argparse
import json
from pathlib import Path

import driver_current_native as corrected
import qualify_driver_restore_components as component
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def comparison_gate(comparison):
    manifest = json.loads((comparison/'manifest.json').read_text())
    if manifest['identity']['code'].get(corrected.NAME) != corrected.native.digest(Path(corrected.__file__)):
        raise ValueError('Use the declared current-correction native comparison')
    return manifest


def prepare(comparison):
    comparison_gate(comparison)
    previous = component.CODE
    try:
        component.CODE = sorted(set(component.CODE) | {NAME, 'spice_dispatch.py'})
        with corrected.profile():
            return component.prepare(comparison, 'restore_64_24')
    finally:
        component.CODE = previous


def run(root, jobs=2):
    if type(jobs) is not int or jobs not in [1, 2]:
        raise ValueError('Use one or two independently leased component workers')
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if identity['code'].get(NAME) != component.digest(Path(__file__)):
        raise ValueError('Corrected-driver qualification producer changed')
    for task in manifest['tasks']:
        folder = root/task['id']
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
            raise ValueError('Partial component execution retained; prepare a fresh context')
    comparison_gate(ROOT/identity['comparison'])
    policy = dict(manifest_sha256=component.digest(root/'manifest.json'), max_jobs=jobs, priority=1,
        global_slot_budget=6, no_outer_lease=True, producer_sha256=component.digest(Path(__file__)),
        dispatcher_sha256=component.digest(ROOT/'scripts/spice_dispatch.py'))
    import hashlib
    out = root/'execution_scheduling'/hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True); capture_manifest(out/'manifest.json', policy)
    previous = component.slot
    try:
        component.slot = lambda: lease(ROOT, priority=1, label='driver_current_qualification')
        with corrected.profile():
            # The original runner remeasures the completed matched native
            # comparison and retains its exact thirty-case coverage gate.
            component.run(root, jobs)
    finally:
        component.slot = previous


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--jobs', type=int, choices=[1, 2], default=2); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve(), a.jobs)
