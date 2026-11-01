#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate a 1 ps maximum step in one original three-variant restoration DC case."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

import receiver_restore_threshold as source
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def tighten(deck):
    matches = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(matches) != 1 or matches[0][0].split() not in [
            ['.tran', '10p', '144n', '0', '50p'], ['.tran', '10p', '144n', '0', '1p']]:
        raise ValueError('Require the original full 144 ns/10 ps static fixture')
    match = matches[0]
    return deck[:match.start()]+re.sub(r'\S+$', '1p', match[0])+deck[match.end():]


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_restore_threshold'):
        raise ValueError('Use an original matched three-variant static context')
    manifest = json.loads((parent/'manifest.json').read_text()); identity = copy.deepcopy(manifest['identity'])
    if (identity['code'].get('receiver_restore_threshold.py') != source.sha(Path(source.__file__)) or
            'numerical_retry_parent' in identity or [t['id'] for t in manifest['tasks']] != source.VARIANTS):
        raise ValueError('Require the original restoration producer and every original variant')
    paths = [parent/'manifest.json']
    for task in manifest['tasks']:
        for name, h in task['files'].items():
            p = parent/task['id']/name
            if source.sha(p) != h:
                raise ValueError('Original restoration source or fixture changed')
            paths.append(p)
    proofs = dict(identity['inputs'], **{str(p.relative_to(ROOT)): source.sha(p) for p in paths})
    if any(source.sha(ROOT/n) != h for n,h in proofs.items()) or any(
            source.sha(ROOT/'scripts'/n) != h for n,h in identity['code'].items()):
        raise ValueError('Original static context changed')
    if source.provenance() != identity['simulator_provenance']:
        raise ValueError('Use the original pinned static simulator runtime')
    identity.update(inputs=proofs, numerical_retry_parent=str(parent.relative_to(ROOT)), maximum_step_ps=1,
        original_maximum_step_ps=50,
        scope='Same full original 144 ns/12-point static fixtures and three receiver candidates, with only maximum integration step tightened from 50 ps to 1 ps. Every circuit, supply, input ramp, output step, method, tolerance and observation/scoring routine is retained. Separate numerical diagnostic; no original matrix, source-clock, native or PHY admission is replaced.')
    identity['code'][NAME] = source.sha(Path(__file__))
    root = ROOT/'build/diagnostics/receiver_restore_threshold'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for task in manifest['tasks']:
        old = parent/task['id']; folder = root/task['id']; folder.mkdir(exist_ok=True)
        deck = tighten((old/'bench.cir').read_text()); before = f'.include "{old}/source.spice"'
        if deck.count(before) != 1:
            raise ValueError('Expected one original observed-source inclusion')
        texts = {n: (old/n).read_text() for n in ['candidate.spice', 'source.spice']}
        texts['bench.cir'] = deck.replace(before, f'.include "{folder}/source.spice"')
        for name, text in texts.items():
            p = folder/name
            if p.exists() and p.read_text() != text:
                raise ValueError('Numerical retry context changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=task['id'], files={n: source.sha(folder/n) for n in texts}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if (identity['code'].get(NAME) != source.sha(Path(__file__)) or identity.get('maximum_step_ps') != 1 or
            root.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]):
        raise ValueError('Use an exact prepared 1 ps numerical retry context')
    for task in manifest['tasks']:
        deck = (root/task['id']/'bench.cir').read_text()
        if tighten(deck) != deck:
            raise ValueError('Every retry control requires the same 1 ps maximum step')
    # The original runner preserves its partial-output refusal, fair actual
    # leases, full trace/current/stress measurements and cached-hash checks.
    return source.run(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run']); parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
