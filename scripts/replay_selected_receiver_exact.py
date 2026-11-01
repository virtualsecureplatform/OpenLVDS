#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded-pin replay with further exact resistor-only native RX reduction.

No capacitor, device terminal, source, port, or numerical tolerance is changed.
The sparse DC witness is an algebraic check; calibrated full native transient
comparison is still required before interpreting changed architectures.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path

import replay_selected_receiver_bounded as bounded
from dll_campaign import text_block
from exact_rc_candidate import parse, render, static_signature, witness, math_runtime
from reduce_rc import eliminate
from spice_library import replace
from receiver_static_diagnosis import capture_manifest

replay = bounded.replay
TOP = 'openlvds_ddr_rx'
DEGREE = 8
NAME = Path(__file__).name


def reduce_library(library):
    original = text_block(library, TOP)
    reference = parse(original)
    candidate = deepcopy(reference)
    removed = eliminate(candidate['graph'], candidate['protected'], DEGREE)
    native = render(candidate, DEGREE)
    serialized = parse(native)
    if (static_signature(reference) != static_signature(serialized) or
            reference['protected'] != serialized['protected']):
        raise ValueError('Exact reduction changed protected circuit statements')
    result = witness(reference, serialized)
    if not result['passed']:
        raise ValueError('Independent terminal-admittance witness failed')
    certificate = dict(method='exact positive-conductance star-mesh', degree=DEGREE,
        algebraic_nodes_eliminated=removed, resistors_before=reference['resistors'],
        resistors_after=serialized['resistors'], non_resistor_sha256=static_signature(serialized),
        admittance_witness=result, math_runtime=math_runtime(),
        qualified_phy=False, transient_equivalence_pending=True)
    return replace(library, TOP, native.rstrip()), certificate


@contextmanager
def profile(parent):
    previous_overlay = replay.overlay
    with bounded.profile(parent) as reference:
        previous_code = replay.CODE
        def overlay(*args, **kwargs):
            return reduce_library(previous_overlay(*args, **kwargs))[0]
        try:
            replay.overlay = overlay
            replay.CODE = set(replay.CODE) | {NAME, 'exact_rc_candidate.py'}
            yield reference
        finally:
            replay.overlay = previous_overlay
            replay.CODE = previous_code


def certify(root, reference, headers):
    manifest = json.loads((root/'manifest.json').read_text())
    parent = replay.ROOT/manifest['identity']['parent']
    expected, certificate = reduce_library((parent/'library.spice').read_text())
    if text_block(expected, TOP) != text_block((root/'library.spice').read_text(), TOP):
        raise ValueError('Captured exact native RX differs from certified reduction')
    certificate.update(parent_library_sha256=replay.digest(parent/'library.spice'),
        library_sha256=replay.digest(root/'library.spice'), producer_sha256=replay.digest(Path(__file__)))
    capture_manifest(root/'exact_rx_certificate.json', certificate)
    bounded.certify(root, reference, headers)
    return certificate


def prepare(parent, sanity, control=None):
    with profile(parent) as (reference, headers):
        root = replay.prepare(parent, sanity, control)
        certify(root, reference, headers)
    return root


def run(root, wait_slot=None):
    identity = json.loads((root/'manifest.json').read_text())['identity']
    if identity['code'].get(NAME) != replay.digest(Path(__file__)):
        raise ValueError('Exact replay producer changed')
    parent = replay.ROOT/identity['parent']
    with profile(parent) as (reference, headers):
        certify(root, reference, headers)
        report = replay.run(root, wait_slot)
        certify(root, reference, headers)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--sanity', type=Path)
    p.add_argument('--control', type=Path)
    p.add_argument('--wait-slot', type=int, choices=range(6))
    a = p.parse_args()
    if a.action == 'prepare':
        if a.sanity is None:
            p.error('--sanity is required')
        print(prepare(a.artifact.resolve(), a.sanity.resolve(), a.control.resolve() if a.control else None), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
        print(a.artifact.resolve()/'summary.json', flush=True)
