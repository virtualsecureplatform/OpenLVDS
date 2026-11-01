#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One bounded convergence retry with a 100-iteration transient Newton budget."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import replay_selected_receiver_exact as exact

replay = exact.replay
NAME = Path(__file__).name


def iteration_fixture(text):
    if text.count('\n.tran ') != 1 or 'itl4' in text.lower():
        raise ValueError('Unexpected existing integration policy')
    # More nonlinear solver iterations before rejecting a timestep. This
    # changes effort, not the circuit, error tolerances or maximum timestep.
    return text.replace('\n.tran ', '\n.options itl4=100\n.tran ')


@contextmanager
def profile(parent):
    with exact.profile(parent) as reference:
        previous_fixture, previous_code = replay.fixture, replay.CODE
        try:
            replay.fixture = lambda *a, **kw: iteration_fixture(previous_fixture(*a, **kw))
            replay.CODE = set(replay.CODE) | {NAME}
            yield reference
        finally:
            replay.fixture, replay.CODE = previous_fixture, previous_code


def prepare(parent, sanity, control=None):
    with profile(parent) as (reference, headers):
        root = replay.prepare(parent, sanity, control)
        exact.certify(root, reference, headers)
    return root


def run(root, wait_slot=None):
    identity = json.loads((root/'manifest.json').read_text())['identity']
    if identity['code'].get(NAME) != replay.digest(Path(__file__)):
        raise ValueError('Iteration-budget replay producer changed')
    parent = replay.ROOT/identity['parent']
    with profile(parent) as (reference, headers):
        exact.certify(root, reference, headers)
        report = replay.run(root, wait_slot)
        exact.certify(root, reference, headers)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    p.add_argument('--sanity', type=Path); p.add_argument('--control', type=Path)
    p.add_argument('--wait-slot', type=int, choices=range(6)); a = p.parse_args()
    if a.action == 'prepare':
        if a.sanity is None:
            p.error('--sanity is required')
        print(prepare(a.artifact.resolve(), a.sanity.resolve(), a.control.resolve() if a.control else None), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
        print(a.artifact.resolve()/'summary.json', flush=True)
