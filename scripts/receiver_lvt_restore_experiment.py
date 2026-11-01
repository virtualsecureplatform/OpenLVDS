#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Use the pinned SKY130 LVT NFET only in the first unclamped restoration stage."""
import argparse
from pathlib import Path
import re

import receiver_clamp_experiment as experiment
from receiver_unclamped_restore_experiment import source_variant as previous_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP = 'openlvds_receiver_core'
HELPER = 'lvds_rx_restore_lvt'


def lower_first_nfet(source):
    definitions = circuits(source)
    rows = {r[0]: r for r in definitions[TOP][1]}
    if rows['XIB0'][1:] != (['CO', 'RESTORE0', 'VDDD', 'VSS'], 'lvds_rx_restore_mid', {}):
        raise ValueError('Unexpected first restoration stage')
    if any(name.startswith('XCLAMP') for name in rows) or HELPER in definitions:
        raise ValueError('Expected unclamped receiver without an LVT helper')
    expected = [('XP', ['Y', 'A', 'VDD', 'VDD'], 'sky130_fd_pr__pfet_01v8', dict(w='8', l='0.15')),
                ('XN', ['Y', 'A', 'VSS', 'VSS'], 'sky130_fd_pr__nfet_01v8', dict(w='4', l='0.15'))]
    if definitions['lvds_rx_restore_mid'] != (['A', 'Y', 'VDD', 'VSS'], expected):
        raise ValueError('Unexpected first-stage transistor sizes or connections')
    helper = text_block(source, 'lvds_rx_restore_mid').replace('lvds_rx_restore_mid', HELPER)
    helper = helper.replace('sky130_fd_pr__nfet_01v8 ', 'sky130_fd_pr__nfet_01v8_lvt ')
    block = text_block(source, TOP)
    block, count = re.subn(r'(?m)^(XIB0[^\n]*)lvds_rx_restore_mid$', r'\1' + HELPER, block)
    if count != 1:
        raise ValueError('Ambiguous first restoration binding')
    return replace(source, TOP, block) + '\n' + helper + '\n'


def source_variant(source, clamped=True):
    source = previous_source(source, clamped)
    return lower_first_nfet(source) if clamped else source


def prepare(parent):
    previous_code = experiment.CODE
    previous_factory = experiment.source_variant
    try:
        experiment.CODE = sorted(set(previous_code) | {'receiver_unclamped_restore_experiment.py',
            'receiver_fast_restore_experiment.py', 'receiver_vref_clamp_experiment.py',
            'receiver_light_clamp_experiment.py', 'receiver_light_decision_experiment.py',
            'receiver_strong_clamp_experiment.py', Path(__file__).name})
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
