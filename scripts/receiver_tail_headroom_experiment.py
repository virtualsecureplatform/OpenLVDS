#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reduce only the unclamped receiver decision-tail width to recover branch headroom."""
import argparse
from pathlib import Path
import re

import receiver_clamp_experiment as experiment
from receiver_unclamped_restore_experiment import source_variant as previous_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP = 'openlvds_receiver_core'


def reduce_decision_tail(source):
    rows = {row[0]: row for row in circuits(source)[TOP][1]}
    expected = ('XCT', ['CT', 'NBC', 'VSS', 'VSS'], 'sky130_fd_pr__nfet_01v8', dict(w='64', l='0.5'))
    if rows.get('XCT') != expected or any(name.startswith('XCLAMP') for name in rows):
        raise ValueError('Expected original decision tail in an unclamped receiver')
    block = text_block(source, TOP)
    block, count = re.subn(r'(?m)^(XCT[^\n]*\bw=)64(\s+l=0\.5\s*)$', r'\g<1>16\2', block)
    if count != 1:
        raise ValueError('Ambiguous decision-tail width')
    return replace(source, TOP, block)


def source_variant(source, clamped=True):
    base = previous_source(source, True)
    return reduce_decision_tail(base) if clamped else base


def prepare(parent):
    previous_code, previous_factory = experiment.CODE, experiment.source_variant
    try:
        experiment.CODE = sorted(set(previous_code) | {
            'receiver_unclamped_restore_experiment.py', 'receiver_fast_restore_experiment.py',
            'receiver_vref_clamp_experiment.py', 'receiver_light_clamp_experiment.py',
            'receiver_light_decision_experiment.py', 'receiver_strong_clamp_experiment.py',
            Path(__file__).name})
        experiment.source_variant = source_variant
        return experiment.prepare(parent)
    finally:
        experiment.CODE, experiment.source_variant = previous_code, previous_factory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        experiment.run(args.artifact.resolve())
