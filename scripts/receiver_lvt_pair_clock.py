#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify original source-clock controls for the low-threshold decision input pair."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import receiver_clamp_experiment as engine
import receiver_decision_load_clock as clock
import receiver_lvt_pair_experiment as factory
import receiver_lvt_pair_matrix as dc

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name


def static_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_matrix'):
        raise ValueError('Use the low-threshold decision-pair DC matrix')
    manifest=json.loads((screen/'manifest.json').read_text());children=manifest['identity']['children']
    if (len(children)!=15 or not (screen/'summary.json').exists() or
            any(not (ROOT/c['root']/'summary.json').exists() for c in children)):
        raise ValueError('Complete all fifteen LVT decision-pair DC cases before source clocks')
    with (screen/'.clock_admission.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);report=dc.run(screen)
    if report.get('required')!=15 or report.get('dc_all_passed') is not True:
        raise ValueError('LVT decision-pair DC matrix must pass all original cases')
    paths=[screen/'manifest.json',screen/'summary.json']
    for child in children:
        folder=ROOT/child['root'];paths.extend(folder/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn'])
    return {str(p.relative_to(ROOT)):factory.digest(p) for p in paths}


@contextmanager
def clock_profile():
    previous_factory,previous_gate=clock.factory,clock.static_gate
    try:
        # Existing immutable clock machinery owns full 80 ns reconstruction,
        # 1 ps integration, waveform checks and all three 47-period gates.
        clock.factory=SimpleNamespace(source_variant=factory.source_variant,experiment=engine)
        clock.static_gate=static_gate
        yield
    finally:clock.factory,clock.static_gate=previous_factory,previous_gate


def prepare(parent,screen):
    proofs=static_gate(screen)
    inherited_code={name for path in proofs if path.endswith('/manifest.json')
        for name in json.loads((ROOT/path).read_text())['identity'].get('code',{})}
    previous_code,previous_factory=engine.CODE,engine.source_variant
    try:
        engine.CODE=sorted(set(previous_code)|set(factory.CODE)|inherited_code|{NAME,'receiver_decision_load_clock.py',
            'receiver_lvt_pair_matrix.py','receiver_decision_load_matrix.py','receiver_tail_timestep_retry.py'})
        engine.source_variant=factory.source_variant
        base=engine.prepare(parent)
    finally:engine.CODE,engine.source_variant=previous_code,previous_factory
    return clock.derive(base,screen,proofs)


def run(root,wait_slot=None):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME)!=factory.digest(Path(__file__)):
        raise ValueError('LVT decision-pair source clock producer changed')
    with clock_profile():clock.run(root,wait_slot)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--dc-matrix',type=Path);parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':
        if args.dc_matrix is None:parser.error('--dc-matrix is required for preparation')
        print(prepare(args.artifact.resolve(),args.dc_matrix.resolve()),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
