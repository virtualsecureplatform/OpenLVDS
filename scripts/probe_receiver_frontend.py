#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay the unchanged source stimuli through the frontend-local LVT layout."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re

import probe_receiver_lvt_compact as native
from layout_receiver_frontend import PROFILE
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def frontend_nodes(model):
    result = []
    for leaf in ['NL', 'NR', 'PL', 'PR', 'NT', 'PT']:
        found = sorted(set(re.findall(r'\bopenlvds_receiver_core__'+leaf+r'(?:\.(?:t|n)\d+)?\b', model)))
        if not found:
            raise ValueError('Missing native frontend observation '+leaf)
        result.append('XRC:'+found[0])
    return result


def add_probes(deck, nodes):
    lines = list(re.finditer(r'(?im)^\.print tran[^\n]*$', deck))
    if len(lines) != 1:
        raise ValueError('Expected one original native replay print statement')
    missing = [n for n in nodes if 'V('+n+')' not in lines[0][0]]
    at = lines[0].end()
    return deck[:at]+(' '+' '.join('V('+n+')' for n in missing) if missing else '')+deck[at:]


@contextmanager
def profile(model):
    previous = native.PROFILE, native.CODE, native.replay_deck, native.lease
    tighten = native.replay_deck; nodes = frontend_nodes(model)
    try:
        native.PROFILE = PROFILE
        native.CODE = sorted(set(native.CODE) | {NAME, 'layout_receiver_frontend.py',
            'receiver_frontend_geometry.py', 'spice_dispatch.py'})
        native.replay_deck = lambda deck, step: add_probes(tighten(deck, step), nodes)
        native.lease = lambda wait_slot=None: lease(ROOT, priority=1, label='native_frontend_local_receiver')
        yield nodes
    finally:
        native.PROFILE, native.CODE, native.replay_deck, native.lease = previous


def prepare(parent, layout, matrix, clock):
    info = json.loads((layout/'extraction.json').read_text()); model = native.checked_netlist(info)
    with profile(model) as nodes:
        root = native.prepare(parent, layout, matrix, clock)
        for task in json.loads((root/'manifest.json').read_text())['tasks']:
            native.ProbeNetwork((root/'library.spice').read_text()).validate((root/task['id']/'bench.cir').read_text(), nodes)
    return root


def run(root):
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if identity['code'].get(NAME) != native.digest(Path(__file__)):
        raise ValueError('Frontend-local native producer changed')
    policy = dict(manifest_sha256=native.digest(root/'manifest.json'),
        producer_sha256=native.digest(Path(__file__)), dispatcher_sha256=native.digest(ROOT/'scripts/spice_dispatch.py'),
        priority=1, global_slot_budget=6, max_jobs=2, no_outer_lease=True)
    import hashlib
    out = root/'execution_scheduling'/hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True); capture_manifest(out/'manifest.json', policy)
    model = (root/'library.spice').read_text()
    with profile(model):
        native.run(root)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('parent', type=Path); a.add_argument('layout', type=Path)
    a.add_argument('--dc-matrix', type=Path, required=True); a.add_argument('--source-clock', type=Path, required=True)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.parent.resolve(), a.layout.resolve(), a.dc_matrix.resolve(), a.source_clock.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
