#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble completed original DC evidence with one explicit matched SF40 1 ps retry."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import matrix_receiver_restore_threshold as matrix
import retry_receiver_restore_static as retry
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
sha = matrix.pilot.sha


def replacement(original, tightened):
    """Require byte-identical circuits and only the declared transient/include edits."""
    before = json.loads((original/'manifest.json').read_text())
    after = json.loads((tightened/'manifest.json').read_text())
    identity = after['identity']
    if (identity.get('numerical_retry_parent') != str(original.relative_to(ROOT)) or
            identity.get('maximum_step_ps') != 1 or identity.get('original_maximum_step_ps') != 50 or
            identity['code'].get(retry.NAME) != sha(Path(retry.__file__)) or
            [t['id'] for t in before['tasks']] != matrix.pilot.VARIANTS or
            [t['id'] for t in after['tasks']] != matrix.pilot.VARIANTS):
        raise ValueError('Require the exact declared matched 50-to-1 ps static retry')
    for variant in matrix.pilot.VARIANTS:
        a, b = original/variant, tightened/variant
        for name in ['candidate.spice', 'source.spice']:
            if (a/name).read_bytes() != (b/name).read_bytes():
                raise ValueError('Numerical retry changed a circuit or observation meter')
        old = (a/'bench.cir').read_text(); include = f'.include "{a}/source.spice"'
        if old.count(include) != 1 or (b/'bench.cir').read_text() != retry.tighten(old).replace(
                include, f'.include "{b}/source.spice"'):
            raise ValueError('Retry changed more than maximum step and source include path')


def complete(children):
    for child in children:
        folder = ROOT/child['root']
        if any(not (folder/name).is_file() for name in ['summary.json']+
               [v+'/summary.json' for v in matrix.pilot.VARIANTS]):
            raise ValueError('Complete all fifteen selected three-variant cases; admission cannot dispatch missing work')


def prepare(original, tightened):
    if (not original.is_relative_to(ROOT/'build/diagnostics/receiver_restore_threshold_matrix') or
            not tightened.is_relative_to(ROOT/'build/diagnostics/receiver_restore_threshold')):
        raise ValueError('Use the original restoration matrix and isolated static retry')
    old = json.loads((original/'manifest.json').read_text()); identity = copy.deepcopy(old['identity'])
    if 'numerical_recovery' in identity:
        raise ValueError('Use the original matrix, not another recovery')
    matrix.coverage(identity['children'], json.loads((ROOT/'requirements.json').read_text()))
    selected = [c for c in identity['children'] if (c['process'], c['temperature']) == ('sf', 40)]
    if len(selected) != 1:
        raise ValueError('Require exactly one original SF40 condition')
    child = selected[0]; parent = ROOT/child['root']
    if sha(parent/'manifest.json') != child['manifest_sha256']:
        raise ValueError('Original SF40 child manifest changed')
    replacement(parent, tightened)
    child.update(root=str(tightened.relative_to(ROOT)), manifest_sha256=sha(tightened/'manifest.json'))
    complete(identity['children'])
    for c in identity['children']:
        cm = json.loads((ROOT/c['root']/'manifest.json').read_text())
        if (sha(ROOT/c['root']/'manifest.json') != c['manifest_sha256'] or
                cm['identity']['parent'] != c['control'] or
                {t['id']:t['files']['candidate.spice'] for t in cm['tasks']} != identity['candidate_sha256']):
            raise ValueError('Selected DC child/PVT/candidate binding changed')
    if any(sha(ROOT/'scripts'/n) != h for n,h in identity['code'].items()):
        raise ValueError('Original source matrix producer changed')
    identity['numerical_recovery'] = dict(original_matrix=str(original.relative_to(ROOT)),
        original_manifest_sha256=sha(original/'manifest.json'), original_child=str(parent.relative_to(ROOT)),
        original_child_manifest_sha256=sha(parent/'manifest.json'), retry=str(tightened.relative_to(ROOT)),
        retry_manifest_sha256=sha(tightened/'manifest.json'), process='sf', temperature=40, maximum_step_ps=1,
        other_fourteen_maximum_step_ps=50)
    identity['code'].update({n: sha(ROOT/'scripts'/n) for n in [NAME, retry.NAME]})
    identity['scope'] = ('Fifteen original full 144 ns/twelve-point source DC/current/stress cases per variant. '
        'Fourteen retain the original 50 ps maximum step; SF40 uses the separately completed, '
        'matched three-variant 1 ps retry. All candidate and observed-source bytes, supplies, '
        'stimuli, integration method/tolerances and scoring remain unchanged. Every selected '
        'trace must already be complete before cached remeasurement. Original partial outputs '
        'are retained. No original-matrix completion, source-clock/native, timing or PHY admission is inferred.')
    root = ROOT/'build/diagnostics/receiver_restore_threshold_matrix'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False))
    return root


def run(root):
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if (identity['code'].get(NAME) != sha(Path(__file__)) or
            root.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]):
        raise ValueError('Use an exact prepared restoration numerical recovery')
    complete(identity['children'])
    proof = identity['numerical_recovery']
    for path, key in [('original_matrix', 'original_manifest_sha256'),
                      ('original_child', 'original_child_manifest_sha256'), ('retry', 'retry_manifest_sha256')]:
        if sha(ROOT/proof[path]/'manifest.json') != proof[key]:
            raise ValueError('Numerical recovery parent or retry evidence changed')
    replacement(ROOT/proof['original_child'], ROOT/proof['retry'])
    # All selected reports exist; this invokes the unchanged full 15-case,
    # per-variant DC/current/stress admission with scientific remeasurement.
    return matrix.run(root, jobs=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run']); parser.add_argument('artifact', type=Path)
    parser.add_argument('--retry', type=Path); args = parser.parse_args()
    if args.action == 'prepare':
        if args.retry is None:
            parser.error('--retry is required')
        print(prepare(args.artifact.resolve(), args.retry.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
