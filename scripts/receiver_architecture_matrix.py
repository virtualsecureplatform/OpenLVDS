#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run one bounded receiver architecture across the original fifteen DC cases."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from dll_campaign import atomic
from receiver_architectures import VARIANTS
from receiver_decision_load_matrix import selected_cases, PILOTS
import receiver_architecture_observations as observed
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
sha = observed.experiment.digest


def prepare(parent, variant):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_tail_headroom_matrix') or variant not in VARIANTS:
        raise ValueError('Use the completed reduced-tail matrix and a bounded architecture')
    summary = json.loads((parent/'summary.json').read_text())
    if (summary.get('required') != 15 or summary.get('dc_all_passed') is not True or
        summary['manifest_sha256'] != sha(parent/'manifest.json')):
        raise ValueError('All fifteen original control cases must pass first')
    cases = selected_cases(json.loads((parent/'manifest.json').read_text()), json.loads((ROOT/'requirements.json').read_text()))
    children = []
    for case in cases:
        control = ROOT/case['root']
        if not (control/'summary.json').is_file() or sha(control/'manifest.json') != case['manifest_sha256']:
            raise ValueError('A completed reduced-tail control is missing or changed')
        child = observed.prepare(control, variant)
        children.append(dict(case=case['case'], process=case['process'], temperature=case['temperature'],
            control=case['root'], root=str(child.relative_to(ROOT)), manifest_sha256=sha(child/'manifest.json')))
    names = set(observed.experiment.CODE) | {NAME, 'receiver_architecture_observations.py', 'receiver_decision_load_matrix.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), variant=variant, children=children,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in [parent/'manifest.json', parent/'summary.json', ROOT/'requirements.json']},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)})
    root = ROOT/'build/diagnostics/receiver_architecture_matrix'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_matrix'):
        raise ValueError('Use a prepared bounded architecture matrix')
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or
            any(sha(ROOT/n) != h for n, h in identity['inputs'].items()) or
            any(sha(ROOT/'scripts'/n) != h for n, h in identity['code'].items())):
            raise ValueError('Architecture matrix context changed')
        cases = selected_cases(json.loads((ROOT/identity['parent']/'manifest.json').read_text()), json.loads((ROOT/'requirements.json').read_text()))
        if [(c['case'], c['root']) for c in cases] != [(c['case'], c['control']) for c in identity['children']]:
            raise ValueError('Architecture matrix coverage changed')
        for child in identity['children']:
            path = ROOT/child['root']; m = json.loads((path/'manifest.json').read_text())
            if (sha(path/'manifest.json') != child['manifest_sha256'] or
                m['identity']['architecture_variant'] != identity['variant'] or m['identity']['parent'] != child['control']):
                raise ValueError('Architecture matrix child changed')
    policy = dict(matrix_manifest_sha256=stamp, producer_sha256=sha(Path(__file__)),
        dispatcher_sha256=sha(ROOT/'scripts/spice_dispatch.py'), priority=1, max_jobs=1,
        global_slot_budget=6, no_outer_lease=True, scope='Resource-only child lease adapter; original scientific fixtures and identities unchanged')
    scheduling = root/'execution_scheduling'/hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    scheduling.mkdir(parents=True, exist_ok=True); capture_manifest(scheduling/'manifest.json', policy)
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        original = observed.experiment.lease
        try:
            observed.experiment.lease = lambda wait_slot=None: lease(ROOT, priority=1, label='architecture_dc_'+identity['variant'])
            for child in identity['children']:
                unchanged()
                if sha(ROOT/'scripts/spice_dispatch.py') != policy['dispatcher_sha256']:
                    raise ValueError('Resource dispatcher changed')
                atomic(root/'state.json', dict(status='running_dc', case=child['case'], completed=len(results), qualified_phy=False))
                report = observed.run(ROOT/child['root'])
                if report.get('diagnostic_complete') is not True or report['manifest_sha256'] != child['manifest_sha256']:
                    raise ValueError('Architecture DC result is incomplete')
                passed = bool(report['architecture']['metrics']['passed'] and report['architecture']['observations']['observed_thin_guard_passed'])
                results.append(dict(case=child['case'], passed=passed, summary_sha256=sha(ROOT/child['root']/'summary.json')))
                if len(results) <= len(PILOTS) and not passed:
                    raise ValueError('Architecture pilot failed; remaining DC cases held')
        except Exception as error:
            atomic(root/'state.json', dict(status='held_for_diagnosis', completed=len(results), error=str(error), qualified_phy=False))
            raise
        finally:
            observed.experiment.lease = original
        unchanged()
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp,
            required=15, dc_all_passed=len(results) == 15 and all(r['passed'] for r in results), results=results,
            scope='One bounded architecture, fifteen original fixed-supply DC cases with current and six-device stress observations. Dynamic/native/remaining-device/PHY qualification remains required.')
        capture_manifest(root/'summary.json', report)
        atomic(root/'state.json', dict(status='complete', completed=len(results), qualified_phy=False))
        return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--variant', choices=VARIANTS); a = p.parse_args()
    if a.action == 'prepare':
        if a.variant is None:
            p.error('--variant is required')
        print(prepare(a.artifact.resolve(), a.variant), flush=True)
    else:
        print(json.dumps(run(a.artifact.resolve())), flush=True)
