#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the matched clamp-removal DC diagnosis at every required PVT point."""
import argparse
import fcntl
import hashlib
import itertools
import json
from pathlib import Path

from dll_campaign import atomic
import receiver_static_diagnosis as diagnosis

ROOT = Path(__file__).resolve().parents[1]


def selected_cases(manifest, requirements):
    tasks = [t for t in manifest['tasks'] if t['view'] == 'schematic' and t['test'] == 'receiver']
    expected = set(itertools.product(requirements['process_corners'], requirements['temperatures_c']))
    actual = [(t['process'], t['temperature']) for t in tasks]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('Incomplete or duplicate matched DC PVT coverage')
    if any(t['id'] != f"schematic_receiver_{t['process']}_{t['temperature']}" for t in tasks):
        raise ValueError('Matched DC case name differs from its PVT point')
    return tasks


def prepare(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/receiver_components'):
        raise ValueError('Use an isolated completed receiver component campaign')
    manifest = json.loads((parent / 'manifest.json').read_text())
    tasks = selected_cases(manifest, json.loads((ROOT / 'requirements.json').read_text()))
    # Each child independently verifies its original waveform, fixture,
    # producers and runtime before cloning only the two-resistor intervention.
    children = [diagnosis.prepare(parent, task['id']) for task in tasks]
    identity = dict(parent=str(parent.relative_to(ROOT)),
        producer_sha256=diagnosis.digest(Path(__file__)),
        requirements_sha256=diagnosis.digest(ROOT / 'requirements.json'),
        parent_manifest_sha256=diagnosis.digest(parent / 'manifest.json'),
        children=[dict(case=task['id'], process=task['process'], temperature=task['temperature'],
                       root=str(child.relative_to(ROOT)), manifest_sha256=diagnosis.digest(child / 'manifest.json'))
                  for task, child in zip(tasks, children)])
    root = ROOT / 'build/diagnostics/receiver_static_matrix' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    atomic(root / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT / 'build/diagnostics/receiver_static_matrix'):
        raise ValueError('Use a prepared matched DC matrix')
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = manifest['identity']
    parent = ROOT / identity['parent']

    def unchanged():
        if (diagnosis.digest(Path(__file__)) != identity['producer_sha256'] or
                diagnosis.digest(ROOT / 'requirements.json') != identity['requirements_sha256'] or
                diagnosis.digest(parent / 'manifest.json') != identity['parent_manifest_sha256']):
            raise ValueError('Matched DC matrix context changed')
        tasks = selected_cases(json.loads((parent / 'manifest.json').read_text()),
                               json.loads((ROOT / 'requirements.json').read_text()))
        if [(t['id'], t['process'], t['temperature']) for t in tasks] != [
                (c['case'], c['process'], c['temperature']) for c in identity['children']]:
            raise ValueError('Matched DC matrix selection changed')
        for child in identity['children']:
            path = (ROOT / child['root']).resolve()
            if (not path.is_relative_to(ROOT / 'build/diagnostics/receiver_static_diagnosis') or
                    diagnosis.digest(path / 'manifest.json') != child['manifest_sha256']):
                raise ValueError('Matched DC child changed')
            selected = json.loads((path / 'manifest.json').read_text())['identity']
            if selected['parent'] != identity['parent'] or selected['case'] != child['case']:
                raise ValueError('Matched DC child selects another source fixture')

    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        results = []
        for child in identity['children']:
            unchanged()
            path = ROOT / child['root']
            atomic(root / 'state.json', dict(status='running_matched_dc_cases', case=child['case'],
                                             completed=len(results), qualified_phy=False))
            # A child owns a shared lease only for its actual simulator run.
            # Cached children remeasure their actual original/modified traces.
            diagnosis.run(path)
            report = json.loads((path / 'summary.json').read_text())
            if report['manifest_sha256'] != child['manifest_sha256'] or not report['diagnostic_complete']:
                raise ValueError('Matched DC child report is incomplete')
            results.append(dict(case=child['case'], process=child['process'], temperature=child['temperature'],
                original_passed=report['original']['metrics']['passed'],
                clamp_removed_passed=report['clamp_removed']['metrics']['passed'],
                report=str((path / 'summary.json').relative_to(ROOT)),
                report_sha256=diagnosis.digest(path / 'summary.json')))
        unchanged()
        atomic(root / 'summary.json', dict(diagnostic_complete=True, qualified_phy=False,
            manifest_sha256=diagnosis.digest(root / 'manifest.json'), required=len(identity['children']),
            dc_all_passed=all(r['clamp_removed_passed'] for r in results), results=results,
            scope='Matched source static DC PVT only; no native timing, rate, aperture or PHY qualification'))
        atomic(root / 'state.json', dict(status='complete', qualified_phy=False, completed=len(results)))
    print(root / 'summary.json', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
