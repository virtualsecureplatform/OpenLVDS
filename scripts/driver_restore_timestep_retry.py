#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retry the matched driver ratio comparison with a stricter 20 ps maximum step."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import re

import driver_restore_experiment as comparison
from reduce_rc import number

ORIGINAL_FIXTURE = comparison.fixture


def fixture(parent_deck, parent, folder):
    deck, probes = ORIGINAL_FIXTURE(parent_deck, parent, folder)
    matches = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(matches) != 1:
        raise ValueError('Expected one original transient command')
    match = matches[0]
    fields = match[0].split()
    if (len(fields) != 5 or number(fields[1]) != 20e-12 or number(fields[3]) != 0 or
            number(fields[4]) != 100e-12):
        raise ValueError('Expected original 20 ps output / 100 ps maximum step')
    # Preserve every original token and space except the maximum integration step.
    command, count = re.subn(r'\S+(\s*)$', r'20p\1', match[0])
    if count != 1:
        raise ValueError('Ambiguous maximum integration step')
    return deck[:match.start()] + command + deck[match.end():], probes


@contextmanager
def selection():
    previous_code, previous_fixture = comparison.CODE, comparison.fixture
    try:
        comparison.CODE = sorted(set(previous_code) | {Path(__file__).name})
        comparison.fixture = fixture
        yield
    finally:
        comparison.CODE, comparison.fixture = previous_code, previous_fixture


def run(action, artifact):
    with selection():
        if action == 'prepare':
            result = comparison.prepare(artifact)
            print(result, flush=True)
            return result
        if action == 'run':
            return comparison.run(artifact)
        raise ValueError('Unknown driver comparison action')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    run(args.action, args.artifact.resolve())
