#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Select the unclamped receiver in unchanged component and loaded-link checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import qualify_receiver_components as components
import probe_receiver_candidate_link as link
import probe_receiver_unclamped_restore_candidate as native
import probe_receiver_lvt_restore_candidate as lvt_native
import probe_receiver_tail_headroom_candidate as tail_native
from receiver_unclamped_restore_experiment import source_variant
from receiver_lvt_restore_experiment import source_variant as lvt_source
from receiver_tail_headroom_experiment import source_variant as tail_source

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {'unclamped_fast_restore': (source_variant, native, 'sky130_fd_pr__nfet_01v8'),
            'unclamped_lvt_restore': (lvt_source, lvt_native, 'sky130_fd_pr__nfet_01v8_lvt'),
            'unclamped_tail_headroom': (tail_source, tail_native, 'sky130_fd_pr__nfet_01v8')}


def selected_replay(replay):
    if not replay.is_relative_to(ROOT / 'build/diagnostics/receiver_replay'):
        raise ValueError('Use an isolated unclamped receiver replay')
    identity = json.loads((replay / 'manifest.json').read_text())['identity']
    profile = PROFILES.get(identity.get('clamp_variant'))
    if (profile is None or
            identity.get('decision_clamped') is not False or identity.get('parallel_clamp_units') != 0 or
            identity.get('clamp_reference') is not None or identity.get('replica_monitor_unloaded') is not True or
            identity.get('input_tail_scale') != 2 or identity.get('decision_scale') != 1 or
            identity.get('restoration_widths_um') != [[8, 4], [16, 8], [16, 8]]):
        raise ValueError('Expected the exact unclamped stronger-restoration receiver')
    declared = identity.get('first_restoration_nfet_model', 'sky130_fd_pr__nfet_01v8')
    if declared != profile[2]:
        raise ValueError('Unclamped restoration NFET model differs from its selected profile')
    if identity['clamp_variant']=='unclamped_tail_headroom':
        if (identity.get('decision_tail_width_um')!=16 or identity.get('decision_tail_scale')!=0.25 or
                identity.get('first_restoration_nfet_model')!='sky130_fd_pr__nfet_01v8'):
            raise ValueError('Reduced decision-tail profile needs its exact width, scale and NFET model')
    elif identity.get('decision_tail_width_um',64)!=64 or identity.get('decision_tail_scale',1)!=1:
        raise ValueError('Decision-tail metadata differs from its selected profile')
    return identity


def recheck(replay):
    identity = selected_replay(replay)
    return PROFILES[identity['clamp_variant']][1].run(replay)


@contextmanager
def selection(replay):
    identity = selected_replay(replay)
    factory, verifier, _ = PROFILES[identity['clamp_variant']]
    changes = [(components, 'CODE', sorted(set(components.CODE) | {Path(__file__).name} | set(verifier.CODE))),
               (link, 'CODE', sorted(set(link.CODE) | {Path(__file__).name} | set(verifier.CODE))),
               (link, 'source_variant', factory), (link, 'recheck_replay', recheck)]
    previous = [(module, name, getattr(module, name)) for module, name, _ in changes]
    try:
        for module, name, value in changes:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in reversed(previous):
            setattr(module, name, value)


def run(action, artifact, replay=None, jobs=3):
    if action.startswith('prepare-'):
        if replay is None:
            raise ValueError('Preparation needs the selected native replay')
    else:
        kind = 'receiver_components' if action == 'run-components' else 'receiver_candidate_link'
        if not artifact.is_relative_to(ROOT / 'build/diagnostics' / kind):
            raise ValueError('Use prepared unclamped receiver diagnostics')
        identity = json.loads((artifact / 'manifest.json').read_text())['identity']
        if Path(__file__).name not in identity['code']:
            raise ValueError('Diagnostic was not prepared with the unclamped selector')
        replay = ROOT / identity['replay']
    with selection(replay):
        if action == 'prepare-components':
            result = components.prepare(artifact, replay)
        elif action == 'prepare-link':
            result = link.prepare(artifact, replay)
        elif action == 'run-components':
            return components.run(artifact, jobs)
        elif action == 'run-link':
            return link.run(artifact)
        else:
            raise ValueError('Unknown unclamped qualification action')
    print(result, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare-components', 'prepare-link', 'run-components', 'run-link'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--jobs', type=int, choices=range(1, 7), default=3)
    args = parser.parse_args()
    run(args.action, args.artifact.resolve(), args.replay.resolve() if args.replay else None, args.jobs)
