#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Gate the low-threshold decision-pair receiver across all original source DC corners."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from dll_campaign import atomic
from receiver_decision_load_matrix import selected_cases,PILOTS
import receiver_lvt_pair_experiment as diagnosis
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_tail_headroom_matrix'):
        raise ValueError('Use the completed reduced-tail source DC matrix')
    manifest=json.loads((parent/'manifest.json').read_text())
    cases=selected_cases(manifest,json.loads((ROOT/'requirements.json').read_text()))
    children=[]
    for case in cases:
        control=(ROOT/case['root']).resolve()
        if (not control.is_relative_to(ROOT/'build/diagnostics/receiver_tail_headroom_static') or
                diagnosis.digest(control/'manifest.json')!=case['manifest_sha256']):
            raise ValueError('Reduced-tail control manifest changed')
        child=diagnosis.prepare(control)
        children.append(dict(case=case['case'],process=case['process'],temperature=case['temperature'],
            control=case['root'],root=str(child.relative_to(ROOT)),manifest_sha256=diagnosis.digest(child/'manifest.json')))
    identity=dict(parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=diagnosis.digest(parent/'manifest.json'),
        requirements_sha256=diagnosis.digest(ROOT/'requirements.json'),producer_sha256=diagnosis.digest(Path(__file__)),
        code={n:diagnosis.digest(ROOT/'scripts'/n) for n in set(diagnosis.CODE)|{'receiver_decision_load_matrix.py'}},children=children)
    root=ROOT/'build/diagnostics/receiver_lvt_pair_matrix'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True);capture_manifest(root/'manifest.json',dict(identity=identity,qualified_phy=False))
    return root


def pilot_gate(children,wait_slot):
    if any(not (ROOT/c['root']/'summary.json').exists() for c in children[:len(PILOTS)]):
        raise ValueError('Complete all three low-threshold decision-pair pilots before remaining DC simulations')
    passed=[]
    for child in children[:len(PILOTS)]:
        result=diagnosis.run(ROOT/child['root'],wait_slot)
        if result.get('manifest_sha256')!=child['manifest_sha256'] or result.get('diagnostic_complete') is not True:
            raise ValueError('Low-threshold decision-pair pilot does not prove completion')
        passed.append(result['lvt_decision_pair']['metrics']['passed'])
    if not all(passed):raise ValueError('Low-threshold decision-pair pilot failed; remaining DC simulations are held')


def run(root,wait_slot=None):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_matrix'):
        raise ValueError('Use the prepared low-threshold decision-pair DC matrix')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity'];stamp=diagnosis.digest(root/'manifest.json')
    def unchanged():
        parent=(ROOT/identity['parent']).resolve()
        if (not parent.is_relative_to(ROOT/'build/diagnostics/receiver_tail_headroom_matrix') or
                diagnosis.digest(root/'manifest.json')!=stamp or diagnosis.digest(Path(__file__))!=identity['producer_sha256'] or
                diagnosis.digest(ROOT/'requirements.json')!=identity['requirements_sha256'] or
                diagnosis.digest(parent/'manifest.json')!=identity['parent_manifest_sha256'] or
                any(diagnosis.digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items())):
            raise ValueError('Low-threshold decision-pair matrix context changed')
        cases=selected_cases(json.loads((parent/'manifest.json').read_text()),json.loads((ROOT/'requirements.json').read_text()))
        if [(c['case'],c['process'],c['temperature'],c['root']) for c in cases]!=[
                (c['case'],c['process'],c['temperature'],c['control']) for c in identity['children']]:
            raise ValueError('Low-threshold decision-pair matrix selection changed')
        for child in identity['children']:
            path=(ROOT/child['root']).resolve()
            if (not path.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_static') or
                    diagnosis.digest(path/'manifest.json')!=child['manifest_sha256'] or
                    json.loads((path/'manifest.json').read_text())['identity']['parent']!=child['control']):
                raise ValueError('Low-threshold decision-pair matrix child changed')
    results=[]
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            unchanged();pilot_gate(identity['children'],wait_slot);unchanged()
            for child in identity['children']:
                unchanged();atomic(root/'state.json',dict(status='running_full_dc',case=child['case'],completed=len(results),qualified_phy=False))
                result=diagnosis.run(ROOT/child['root'],wait_slot)
                if result.get('manifest_sha256')!=child['manifest_sha256'] or result.get('diagnostic_complete') is not True:
                    raise ValueError('Low-threshold decision-pair child report incomplete')
                results.append(dict(case=child['case'],passed=result['lvt_decision_pair']['metrics']['passed'],
                    report_sha256=diagnosis.digest(ROOT/child['root']/'summary.json')))
            unchanged()
            summary=dict(diagnostic_complete=True,qualified_phy=False,manifest_sha256=stamp,required=len(results),
                dc_all_passed=all(r['passed'] for r in results),results=results,
                scope='Low-threshold decision-pair decision source DC only; source clock, physical/native/components and PHY gates remain')
            atomic(root/'summary.json',summary);atomic(root/'state.json',dict(status='complete',completed=len(results),qualified_phy=False))
        except Exception as error:
            atomic(root/'state.json',dict(status='held_for_diagnosis',completed=len(results),qualified_phy=False,error=str(error)));raise
    print(root/'summary.json',flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve()),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
