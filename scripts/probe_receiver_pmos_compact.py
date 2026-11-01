#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reuse the strict native replay machinery for the admitted compact PMOS receiver."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import probe_receiver_lvt_compact as native
import receiver_pmos_clock as source_clock

NAME = Path(__file__).name
PROFILE = dict(architecture_variant=source_clock.VARIANT,
    clamp_variant='unclamped_architecture_compact',
    diagnostic_stage='three_passing_source_DC_pilots_and_nominal_rate',
    placement='Four folded frontend columns on shared M4 trunks; packed summing/decision/restoration row; critical M3 buses first')
SCOPE = 'Native compact PMOS p8/t4 experiment with original pin stimuli and RX load; full source DC and source-clock admission required. No native PVT/component, remaining-device stress, aperture or link qualification.'


@contextmanager
def profile():
    previous = native.PROFILE, native.CODE, native.source_variant, native.source_clock, native.atomic
    write = native.atomic
    def atomic(path, value):
        # Adapt only the descriptive root scope. The original runner still
        # computes every pulse, hash, completeness and native admission flag.
        if str(value.get('scope', '')).startswith('Native compact LVT decision-pair experiment'):
            value = dict(value, scope=SCOPE)
        return write(path, value)
    try:
        native.PROFILE = PROFILE
        native.CODE = sorted(set(native.CODE) | {NAME, 'receiver_pmos_clock.py',
            'receiver_architecture_matrix.py', 'receiver_architecture_experiment.py',
            'receiver_architecture_observations.py', 'receiver_architectures.py', 'layout_receiver_architecture.py'})
        native.source_variant = source_clock.source_variant
        native.source_clock = source_clock
        native.atomic = atomic
        yield
    finally:
        native.PROFILE, native.CODE, native.source_variant, native.source_clock, native.atomic = previous


def prepare(parent, layout, matrix, clock):
    with profile():
        return native.prepare(parent, layout, matrix, clock)


def run(root, wait_slots=None):
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != native.digest(Path(__file__)):
        raise ValueError('PMOS native receiver producer changed')
    with profile():
        native.run(root, wait_slots)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('parent', type=Path); a.add_argument('layout', type=Path)
    a.add_argument('--dc-matrix', type=Path, required=True); a.add_argument('--source-clock', type=Path, required=True)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path)
    a.add_argument('--wait-slot', type=int, choices=range(6), action='append', default=[]); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.parent.resolve(), a.layout.resolve(), a.dc_matrix.resolve(), a.source_clock.resolve()), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
