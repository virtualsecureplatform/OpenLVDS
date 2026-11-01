#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test stronger restoration with the two DC-loading CO clamps removed."""
import argparse
from pathlib import Path
import re

import receiver_clamp_experiment as experiment
from receiver_fast_restore_experiment import source_variant as previous_source
from dll_campaign import text_block
from spice_library import replace

TOP = 'openlvds_receiver_core'


def source_variant(source, clamped=True):
    source = previous_source(source, clamped)
    if not clamped:
        return source
    block = text_block(source, TOP)
    for name in ['XCLAMP0', 'XCLAMP1']:
        pattern = r'(?m)^' + name + r'[^\n]*\n?'
        rows = re.findall(pattern, block)
        expected = [name, 'CO', 'VREF', 'VSS', 'sky130_fd_pr__res_high_po_0p35', 'w=0.35', 'l=1.25']
        if len(rows) != 1 or rows[0].split() != expected:
            raise ValueError('Unexpected CO clamp: ' + name)
        block = re.sub(pattern, '', block)
    return replace(source, TOP, block)


def prepare(parent):
    previous_code = experiment.CODE
    previous_factory = experiment.source_variant
    try:
        experiment.CODE = sorted(set(previous_code) | {'receiver_fast_restore_experiment.py',
            'receiver_vref_clamp_experiment.py', 'receiver_light_clamp_experiment.py',
            'receiver_light_decision_experiment.py', 'receiver_strong_clamp_experiment.py', Path(__file__).name})
        experiment.source_variant = source_variant
        return experiment.prepare(parent)
    finally:
        experiment.CODE = previous_code
        experiment.source_variant = previous_factory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        experiment.run(args.artifact.resolve())
