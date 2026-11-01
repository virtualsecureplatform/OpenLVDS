#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Raise the unclamped comparator input common mode using four existing resistors."""
import argparse
from pathlib import Path
import re

import receiver_clamp_experiment as experiment
from receiver_unclamped_restore_experiment import source_variant as previous_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP = 'openlvds_receiver_core'
RESISTORS = {'XRLPPD': ['PP', 'PPRB', 'VSS'],
             'XRLPPE': ['PPRB', 'VSS', 'VSS'],
             'XRLPND': ['PN', 'PNRB', 'VSS'],
             'XRLPNE': ['PNRB', 'VSS', 'VSS']}


def raise_input_bias(source):
    rows = {row[0]: row for row in circuits(source)[TOP][1]}
    if any(name.startswith('XCLAMP') for name in rows):
        raise ValueError('Expected an unclamped receiver')
    block = text_block(source, TOP)
    for name, nodes in RESISTORS.items():
        expected = (name, nodes, 'sky130_fd_pr__res_high_po_0p35', dict(w='0.35', l='1.25'))
        if rows.get(name) != expected:
            raise ValueError('Unexpected input-load resistor: ' + name)
        pattern = r'(?m)^' + name + r'[^\n]*$'
        line = re.search(pattern, block)[0]
        block, count = re.subn(pattern, lambda _: line.replace('l=1.25', 'l=2.5'), block)
        if count != 1:
            raise ValueError('Ambiguous input-load resistor: ' + name)
    return replace(source, TOP, block)


def source_variant(source, clamped=True):
    # Both controls use the same standard-NFET unclamped fast restoration.
    base = previous_source(source, True)
    return raise_input_bias(base) if clamped else base


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
