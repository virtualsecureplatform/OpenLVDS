#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retry the original matched source drivers with a declared 1 ps maximum step."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re

import driver_restore_experiment as comparison
from dll_campaign import atomic
from reduce_rc import number

NAME = Path(__file__).name
ORIGINAL_FIXTURE = comparison.fixture


def tighten(deck):
    rows = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(rows) != 1:
        raise ValueError('Expected one original driver transient command')
    row = rows[0];fields = row[0].split()
    if (len(fields) != 5 or number(fields[1]) != 20e-12 or
            abs(number(fields[2]) - 188.049e-9) > 1e-18 or number(fields[3]) != 0 or
            number(fields[4]) != 100e-12):
        raise ValueError('Expected original full 188.049 ns, 20 ps output and 100 ps maximum step')
    command = re.sub(r'\S+(\s*)$', r'1p\1', row[0])
    return deck[:row.start()] + command + deck[row.end():]


def fixture(parent_deck, parent, folder):
    deck, probes = ORIGINAL_FIXTURE(parent_deck, parent, folder)
    return tighten(deck), probes


@contextmanager
def selection():
    code, original = comparison.CODE, comparison.fixture
    try:
        comparison.CODE = sorted(set(code) | {NAME})
        comparison.fixture = fixture
        yield
    finally:
        comparison.CODE, comparison.fixture = code, original


def policy(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != comparison.digest(Path(__file__)):
        raise ValueError('Driver precision producer was not captured')
    return dict(qualified_phy=False, manifest_sha256=comparison.digest(root / 'manifest.json'),
                producer_sha256=comparison.digest(Path(__file__)), parent=manifest['identity']['parent'],
                maximum_step_ps=1, original_maximum_step_ps=100, output_step_ps=20, stop_ns=188.049,
                scope='Matched original source driver controls; integration only; original circuit/stimulus/scoring; no PHY qualification')


def run(action, artifact):
    with selection():
        if action == 'prepare':
            root = comparison.prepare(artifact)
            expected = policy(root);path = root / 'numerical_policy.json'
            if path.exists():
                if json.loads(path.read_text()) != expected:
                    raise ValueError('Driver precision policy changed')
            else:
                atomic(path, expected)
            print(root, flush=True)
            return root
        if action == 'run':
            if json.loads((artifact / 'numerical_policy.json').read_text()) != policy(artifact):
                raise ValueError('Driver precision policy changed')
            # The original runner reconstructs both exact 1 ps fixtures and
            # validates all actual deck/library/model/runtime hashes before slots.
            return comparison.run(artifact)
        raise ValueError('Unknown driver precision comparison action')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    run(args.action, args.artifact.resolve())
