#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Gate both receiver gain/balance candidates across the original fifteen source DC PVT cases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path

import receiver_gain_balance as pilot
import receiver_lvt_pair_matrix as baseline
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
PILOTS = [('ss', 40), ('fs', 40), ('sf', 0), ('fs', 0), ('tt', 25), ('sf', 25)]


def coverage(children, requirements):
    expected = {(p, t) for p in requirements['process_corners'] for t in requirements['temperatures_c']}
    actual = [(c['process'], c['temperature']) for c in children]
    if (len(children) != 15 or len(actual) != len(set(actual)) or set(actual) != expected or
            any(c['case'] != f"schematic_receiver_{c['process']}_{c['temperature']}" for c in children)):
        raise ValueError('Require each original process/temperature source case exactly once')


def passed(row):
    return bool(row['passed'] and row['metrics']['metrics']['passed'] and
                row['twelve_device_observations']['observed_thin_guard_passed'])


def admission(results, required=15):
    answer = {}
    for variant in pilot.VARIANTS:
        rows = [next(r for r in c['results'] if r['task'] == variant) for c in results]
        answer[variant] = dict(required=required, completed=len(rows), passed_cases=sum(passed(r) for r in rows),
            source_dc_passed=bool(len(rows) == required and all(passed(r) for r in rows)))
    return answer


def prepare(parent, control_matrix):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_matrix'):
        raise ValueError('Use the completed original LVT source DC matrix')
    m = json.loads((parent/'manifest.json').read_text()); old = m['identity']['children']
    requirements = json.loads((ROOT/'requirements.json').read_text()); coverage(old, requirements)
    if not (parent/'summary.json').is_file() or any(not (ROOT/c['root']/'summary.json').is_file() for c in old):
        raise ValueError('Complete all fifteen original source controls first')
    if baseline.run(parent).get('dc_all_passed') is not True:
        raise ValueError('Original LVT source matrix failed')
    order = lambda c: PILOTS.index((c['process'], c['temperature'])) if (c['process'], c['temperature']) in PILOTS else len(PILOTS)
    children = []; candidates = None
    for c in sorted(old, key=order):
        control = ROOT/c['root']
        if pilot.sha(control/'manifest.json') != c['manifest_sha256']:
            raise ValueError('Original source control manifest changed')
        child = pilot.prepare(control, control_matrix); cm = json.loads((child/'manifest.json').read_text())
        hashes = {t['id']: t['files']['candidate.spice'] for t in cm['tasks']}
        if candidates is not None and candidates != hashes:
            raise ValueError('Different PVT cases use different candidate circuit bytes')
        candidates = hashes
        children.append(dict(case=c['case'], process=c['process'], temperature=c['temperature'],
            control=c['root'], root=str(child.relative_to(ROOT)), manifest_sha256=pilot.sha(child/'manifest.json')))
    identity = dict(control_matrix=str(control_matrix.relative_to(ROOT)), control_manifest_sha256=pilot.sha(control_matrix/'manifest.json'),
        control_summary_sha256=pilot.sha(control_matrix/'summary.json'), parent=str(parent.relative_to(ROOT)), parent_manifest_sha256=pilot.sha(parent/'manifest.json'),
        parent_summary_sha256=pilot.sha(parent/'summary.json'), requirements_sha256=pilot.sha(ROOT/'requirements.json'),
        children=children, candidate_sha256=candidates, pilots=PILOTS,
        code={n: pilot.sha(ROOT/'scripts'/n) for n in [NAME, 'receiver_gain_balance.py', 'receiver_lvt_pair_matrix.py']},
        scope='Fifteen original full-duration source DC/current/stress cases per candidate. SS40/FS40/SF0/FS0/TT25/SF25 pilots gate the remainder. Uniform 1 ps maximum step, same fixed supplies and sensitivity stimuli; source clocks, physical/native components, timing and PHY admission remain required.')
    root = ROOT/'build/diagnostics/receiver_gain_balance_matrix'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False))
    return root


def run(root, jobs=2):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_gain_balance_matrix') or jobs not in [1, 2]:
        raise ValueError('Use a prepared source matrix with one or two independent workers')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = pilot.sha(root/'manifest.json')
    def unchanged():
        coverage(i['children'], json.loads((ROOT/'requirements.json').read_text()))
        parent = ROOT/i['parent']
        if (pilot.sha(ROOT/i['control_matrix']/'manifest.json') != i['control_manifest_sha256'] or
                pilot.sha(ROOT/i['control_matrix']/'summary.json') != i['control_summary_sha256'] or
                pilot.sha(root/'manifest.json') != stamp or pilot.sha(ROOT/'requirements.json') != i['requirements_sha256'] or
                pilot.sha(parent/'manifest.json') != i['parent_manifest_sha256'] or
                pilot.sha(parent/'summary.json') != i['parent_summary_sha256'] or
                any(pilot.sha(ROOT/'scripts'/n) != h for n, h in i['code'].items())):
            raise ValueError('Gain/balance source matrix context changed')
        for c in i['children']:
            child = ROOT/c['root']; cm = json.loads((child/'manifest.json').read_text())
            if (pilot.sha(child/'manifest.json') != c['manifest_sha256'] or cm['identity']['parent'] != c['control'] or
                    {t['id']: t['files']['candidate.spice'] for t in cm['tasks']} != i['candidate_sha256']):
                raise ValueError('Gain/balance child/PVT/candidate binding changed')
    def execute(c):
        unchanged(); report = pilot.run(ROOT/c['root']); unchanged()
        if report.get('diagnostic_complete') is not True or [r['task'] for r in report['results']] != pilot.VARIANTS:
            raise ValueError('Gain/balance child does not prove complete variant coverage')
        return dict(case=c['case'], process=c['process'], temperature=c['temperature'], results=report['results'],
            report_sha256=pilot.sha(ROOT/c['root']/'summary.json'))
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        try:
            if [(c['process'], c['temperature']) for c in i['children'][:len(PILOTS)]] != PILOTS:
                raise ValueError('Require matched SS40/FS40/SF0/FS0/TT25/SF25 pilots before bulk DC')
            for label, batch in [('pilots', i['children'][:len(PILOTS)]), ('full_dc', i['children'][len(PILOTS):])]:
                atomic(root/'state.json', dict(status='running_'+label, completed_pvt=len(results), qualified_phy=False))
                # Children own their individual shared leases; no outer lease.
                with ThreadPoolExecutor(max_workers=jobs) as pool:
                    for result in pool.map(execute, batch):
                        results.append(result)
                        atomic(root/'state.json', dict(status='running_'+label, completed_pvt=len(results), qualified_phy=False))
                if label == 'pilots':
                    gates = admission(results, required=len(PILOTS))
                    capture_manifest(root/'pilot_summary.json', dict(qualified_phy=False, results=results, variants=gates))
                    if not gates['control']['source_dc_passed'] or not any(gates[v]['source_dc_passed'] for v in pilot.VARIANTS if v!='control'):
                        raise ValueError('Control failed or neither gain/balance candidate passed every pilot; bulk held for diagnosis')
            unchanged(); gates = admission(results)
            report = dict(diagnostic_complete=True, qualified_phy=False, required_pvt=15,
                manifest_sha256=stamp, results=results, variants=gates, scope=i['scope'])
            capture_manifest(root/'summary.json', report)
            out = root/'source_dc_admission'; out.mkdir(exist_ok=True)
            for variant, gate in gates.items():
                capture_manifest(out/(variant+'.json'), dict(gate, variant=variant, qualified_phy=False,
                    manifest_sha256=stamp, report_sha256=pilot.sha(root/'summary.json'),
                    candidate_sha256=i['candidate_sha256'][variant],
                    scope='Source DC/current/twelve-observed-device screen only. No source-clock, native, rate, aperture, link or PHY admission.'))
            atomic(root/'state.json', dict(status='completed', completed_pvt=15, qualified_phy=False))
        except Exception as error:
            atomic(root/'state.json', dict(status='held_for_diagnosis', completed_pvt=len(results), error=str(error), qualified_phy=False))
            raise
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    p.add_argument('--control-matrix', type=Path); p.add_argument('--jobs', type=int, choices=[1, 2], default=2); a = p.parse_args()
    if a.action == 'prepare':
        if a.control_matrix is None:
            p.error('--control-matrix is required for preparation')
        print(prepare(a.artifact.resolve(), a.control_matrix.resolve()), flush=True)
    else:
        run(a.artifact.resolve(), a.jobs); print(a.artifact.resolve()/'summary.json', flush=True)
