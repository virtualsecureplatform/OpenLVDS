#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate a stricter 1 ps maximum integration step in the decision-tail clock screen."""
import argparse
import fcntl
import json
from pathlib import Path
import re

import receiver_tail_headroom_experiment as candidate
from dll_campaign import atomic
from receiver_clamp_experiment import digest
from reduce_rc import number

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def tighten(deck):
    matches = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(matches) != 1:
        raise ValueError('Expected one original receiver transient command')
    match = matches[0]
    fields = match[0].split()
    if (len(fields) != 5 or number(fields[1]) != 5e-12 or number(fields[2]) != 80e-9 or
            number(fields[3]) != 0 or number(fields[4]) not in [5e-12, 1e-12]):
        raise ValueError('Expected the original full 80 ns receiver fixture and 5 ps output step')
    if number(fields[4]) == 1e-12:
        return deck
    command = re.sub(r'\S+(\s*)$', r'1p\1', match[0])
    return deck[:match.start()] + command + deck[match.end():]


def policy(root, manifest):
    return dict(qualified_phy=False, manifest_sha256=digest(root/'manifest.json'),
        producer_sha256=digest(Path(__file__)), parent=manifest['identity']['parent'],
        maximum_step_ps=1, original_maximum_step_ps=5, output_step_ps=5, stop_ns=80,
        scope='Original three source receiver controls; stricter integration only; original circuit, stimuli and scoring')


def prepare(parent):
    previous_code = candidate.experiment.CODE
    try:
        candidate.experiment.CODE = sorted(set(previous_code) | {NAME})
        root = candidate.prepare(parent)
    finally:
        candidate.experiment.CODE = previous_code
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        return prepare_controls(root)


def prepare_controls(root):
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != digest(Path(__file__)):
        raise ValueError('Retry producer was not captured')
    changes = []
    for task in manifest['tasks']:
        folder = root/task['id'];path = folder/'bench.cir'
        if any(digest(folder/name)!=stamp for name,stamp in task['files'].items()):
            raise ValueError('Prepared receiver fixture changed')
        before = path.read_text();after = tighten(before)
        if before != after:
            if (root/'numerical_policy.json').exists() or any((root/t['id']/name).exists() for t in manifest['tasks'] for name in
                   ['execution.json', 'summary.json', 'bench.raw', 'bench.cir.prn']):
                raise ValueError('Cannot change an executed receiver fixture')
            changes.append((task, path, after))
    # A new identity already captures this leaf's numerical policy. No original
    # campaign is modified. Re-preparation preserves every existing manifest byte.
    if changes:
        for task,path,after in changes:
            path.write_text(after)
            task['files']['bench.cir'] = digest(path)
        atomic(root/'manifest.json',manifest)
    expected = policy(root,manifest);target = root/'numerical_policy.json'
    if target.exists():
        if json.loads(target.read_text()) != expected:
            raise ValueError('Receiver numerical policy changed')
    else:
        atomic(target,expected)
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use an isolated receiver source comparison')
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != digest(Path(__file__)):
        raise ValueError('Source comparison did not capture this numerical retry')
    if json.loads((root/'numerical_policy.json').read_text()) != policy(root,manifest):
        raise ValueError('Receiver numerical policy changed')
    for task in manifest['tasks']:
        deck = (root/task['id']/'bench.cir').read_text()
        if tighten(deck) != deck:
            raise ValueError('Every retry control needs the same 1 ps maximum step')
    candidate.experiment.run(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('artifact',type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()),flush=True)
    else:
        run(args.artifact.resolve())
