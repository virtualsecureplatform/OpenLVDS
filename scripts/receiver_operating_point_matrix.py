#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure static receiver current/headroom at the original twelve points and fifteen PVT cases."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import analyze_receiver_operating_points as analysis
from dll_campaign import atomic
import receiver_decision_headroom as headroom
import receiver_operating_point_probe as probe
from receiver_static_diagnosis import capture_manifest

ROOT = probe.ROOT
CODE = ['receiver_operating_point_matrix.py', 'analyze_receiver_operating_points.py',
        'receiver_operating_point_probe.py', 'receiver_decision_headroom.py']


def prepare(matrix):
    # This observer remeasures completed source evidence; it cannot launch a
    # missing source transient or admit downstream physical/native work.
    observation, report = headroom.analyze(matrix)
    if not report['all_cases_observed'] or not all(r['logic_passed'] for r in report['results']):
        raise ValueError('Require all fifteen completed passing source DC cases')
    original = json.loads((matrix / 'manifest.json').read_text())
    children = []
    for child in original['identity']['children']:
        folder = probe.prepare(ROOT / child['root'], all_points=True)
        children.append(dict(case=child['case'], process=child['process'], temperature=child['temperature'],
                             root=str(folder.relative_to(ROOT)), manifest_sha256=probe.digest(folder / 'manifest.json')))
    inputs = {str(p.relative_to(ROOT)): probe.digest(p) for p in
              [matrix / 'manifest.json', matrix / 'summary.json', observation / 'manifest.json', observation / 'summary.json', ROOT / 'requirements.json']}
    identity = dict(source=str(matrix.relative_to(ROOT)), children=children, inputs=inputs,
                    code={n: probe.digest(ROOT / 'scripts' / n) for n in CODE})
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / 'build/diagnostics/receiver_operating_point_matrix' / key
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def run_case(folder, wait_slot):
    # Preserve the original simulator/fixture producer. Its capability pilot
    # exposed unit-wrapped vector names. A separate bound analysis handles
    # those names, without changing or rerunning any complete OP evidence.
    with (folder / '.analysis_execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        count = len(json.loads((folder / 'manifest.json').read_text())['identity']['points'])
        complete = all((folder / f'point_{i}.raw').exists() for i in range(count))
        if not complete:
            if (folder / 'ngspice.log').exists() or list(folder.glob('point_*.raw')):
                raise ValueError('Partial operating-point evidence retained; use a fresh context')
            try:
                probe.run(folder, wait_slot)
            except ValueError as error:
                if str(error) != 'Missing requested model/current operating-point vectors':
                    raise
        return analysis.analyze(folder)


def run(folder, wait_slot=None):
    if not folder.is_relative_to(ROOT / 'build/diagnostics/receiver_operating_point_matrix'):
        raise ValueError('Use a prepared receiver operating-point matrix')
    manifest = json.loads((folder / 'manifest.json').read_text())
    identity = manifest['identity']; stamp = probe.digest(folder / 'manifest.json')
    requirements = json.loads((ROOT / 'requirements.json').read_text())
    expected = {(p, t) for p in requirements['process_corners'] for t in requirements['temperatures_c']}
    children = identity['children']
    if len(children) != len(expected) or {(c['process'], c['temperature']) for c in children} != expected:
        raise ValueError('Require exact fifteen-case process/temperature coverage')
    def unchanged():
        if (probe.digest(folder / 'manifest.json') != stamp or
            any(probe.digest(ROOT / 'scripts' / n) != sha for n, sha in identity['code'].items()) or
            any(probe.digest(ROOT / n) != sha for n, sha in identity['inputs'].items())):
            raise ValueError('Operating-point matrix context changed')
        source_children = json.loads((ROOT / identity['source'] / 'manifest.json').read_text())['identity']['children']
        if [(c['case'], c['process'], c['temperature']) for c in children] != [
                (c['case'], c['process'], c['temperature']) for c in source_children]:
            raise ValueError('Operating-point selection differs from source matrix')
        for child, source_child in zip(children, source_children):
            path = (ROOT / child['root']).resolve()
            if (not path.is_relative_to(ROOT / 'build/diagnostics/receiver_operating_points') or
                probe.digest(path / 'manifest.json') != child['manifest_sha256']):
                raise ValueError('Operating-point child changed')
            local = json.loads((path / 'manifest.json').read_text())['identity']
            if local['parent'] != source_child['root']:
                raise ValueError('Operating-point child belongs to another source case')
            if [p['time_ns'] for p in local['points']] != list(range(10, 144, 12)):
                raise ValueError('Require all twelve original static points')
    with (folder / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = []
        try:
            unchanged()
            for child in children:
                atomic(folder / 'state.json', dict(status='measuring_static_points', case=child['case'], completed=len(results), qualified_phy=False))
                out = run_case(ROOT / child['root'], wait_slot)
                measured = json.loads((out / 'summary.json').read_text())
                if measured.get('diagnostic_complete') is not True or len(measured['results']) != 12:
                    raise ValueError('Incomplete static operating-point analysis')
                results.append(dict(case=child['case'], analysis=str(out.relative_to(ROOT)),
                                    report_sha256=probe.digest(out / 'summary.json'), results=measured['results']))
                unchanged()
            capture_manifest(folder / 'summary.json', dict(diagnostic_complete=True, qualified_phy=False,
                manifest_sha256=stamp, required_cases=15, observed_cases=len(results), results=results,
                scope='Original 180 schematic static operating points, fixed supplies. Tail model parameters and receiver/bias rail/reference power; excludes native/dynamic/full-device stress and PHY qualification.'))
            atomic(folder / 'state.json', dict(status='complete', completed=len(results), qualified_phy=False))
        except Exception as error:
            atomic(folder / 'state.json', dict(status='held_for_diagnosis', completed=len(results), error=str(error), qualified_phy=False))
            raise
    return folder / 'summary.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--wait-slot', type=int, choices=range(6))
    args = parser.parse_args()
    print(prepare(args.artifact.resolve()) if args.action == 'prepare' else run(args.artifact.resolve(), args.wait_slot), flush=True)
