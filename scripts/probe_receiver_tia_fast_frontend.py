#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay original pins through the audited faster-frontend feedback receiver."""
import argparse
from contextlib import contextmanager
import json
import re
from pathlib import Path

import layout_receiver_tia_fast_frontend as physical
import probe_receiver_lvt_compact as native
import probe_receiver_frontend as frontend
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def observation_nodes(variant,model):
    if variant not in physical.clocks.VARIANTS:raise ValueError('Select a declared feedback-inverter receiver')
    nodes=frontend.frontend_nodes(model);count=2 if variant=='fast_tia_r2' else 4
    for leaf in ['FB'+str(i) for i in range(1,count)]+['PPRT','PPRB','PNRT','PNRB','PPBOOST1','PNBOOST1']:
        found=sorted(set(re.findall(r'\bopenlvds_receiver_core__'+leaf+r'(?:\.(?:t|n)\d+)?\b',model)))
        if not found:raise ValueError('Missing native feedback-inverter observation '+leaf)
        nodes.append('XRC:'+found[0])
    return nodes


@contextmanager
def profile(variant, model):
    selected = physical.profile(variant)
    nodes = observation_nodes(variant,model)
    previous = native.PROFILE, native.CODE, native.source_gate, native.source_variant, native.replay_deck, native.lease
    replay = native.replay_deck
    try:
        native.PROFILE = selected
        native.CODE = sorted(set(native.CODE) | {NAME, 'layout_receiver_tia_fast_frontend.py',
            'receiver_tia_fast_frontend_clock.py', 'receiver_restore_threshold_clock.py', 'receiver_restore_threshold.py', 'matrix_receiver_tia_fast_frontend.py', 'screen_receiver_tia_fast_frontend.py', 'receiver_tia_fast_frontend.py', 'receiver_differential_restore.py', 'receiver_tia_restore.py', 'receiver_gain_balance.py', 'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py',
            'probe_receiver_frontend.py', 'receiver_frontend_geometry.py', 'receiver_soft_frontend_geometry.py', 'receiver_tia_fast_geometry.py', 'spice_dispatch.py'})
        native.source_gate = lambda screen, clock: physical.source_gate(screen, clock, variant)
        native.source_variant = lambda source, changed: physical.clocks.source_variant(source, changed, variant)
        native.replay_deck = lambda deck, step: frontend.add_probes(replay(deck, step), nodes)
        native.lease = lambda wait_slot=None: lease(ROOT, priority=1, label='native_receiver_differential_restore_'+variant)
        yield nodes
    finally:
        native.PROFILE, native.CODE, native.source_gate, native.source_variant, native.replay_deck, native.lease = previous


def prepare(parent, layout, matrix, clock, variant):
    # Require the new profile and its physical audit before invoking the
    # scientific replay engine. Old geometry cannot substitute for it.
    selected = physical.profile(variant)
    if any(not (layout/n).is_file() for n in ['summary.json', 'extraction.json', 'rc_audit.json', 'candidate.spice']):
        raise ValueError('Complete the selected differential-restoration correction geometry and RC audit before native replay')
    report = json.loads((layout/'summary.json').read_text())
    if any(report['identity'].get(k) != v for k, v in selected.items()):
        raise ValueError('Native replay requires this exact differential-restoration correction physical profile')
    info = json.loads((layout/'extraction.json').read_text()); model = native.checked_netlist(info)
    with profile(variant, model) as nodes:
        root = native.prepare(parent, layout, matrix, clock)
        for task in json.loads((root/'manifest.json').read_text())['tasks']:
            native.ProbeNetwork((root/'library.spice').read_text()).validate((root/task['id']/'bench.cir').read_text(), nodes)
    return root


def run(root):
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if identity['code'].get(NAME) != native.digest(Path(__file__)):
        raise ValueError('Differential-restoration native producer changed')
    with profile(identity['tia_fast_frontend_variant'], (root/'library.spice').read_text()):
        native.run(root)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('parent', type=Path); a.add_argument('layout', type=Path)
    a.add_argument('--dc-matrix', type=Path, required=True); a.add_argument('--source-clock', type=Path, required=True)
    a.add_argument('--variant', choices=physical.clocks.VARIANTS, required=True)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.parent.resolve(), a.layout.resolve(), a.dc_matrix.resolve(), a.source_clock.resolve(), a.variant), flush=True)
    else:
        run(a.artifact.resolve())
