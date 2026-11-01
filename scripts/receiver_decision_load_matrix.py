#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Advance the stronger-PMOS receiver from three pilots to all source DC corners."""
import argparse
import fcntl
import hashlib
import itertools
import json
from pathlib import Path

from dll_campaign import atomic
import receiver_decision_load_static as diagnosis

ROOT=Path(__file__).resolve().parents[1]
PILOTS=[('tt',25),('sf',40),('fs',40)]


def selected_cases(manifest,requirements):
    children=manifest['identity']['children']
    expected=set(itertools.product(requirements['process_corners'],requirements['temperatures_c']))
    actual=[(c['process'],c['temperature']) for c in children]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('Incomplete or duplicate source DC PVT coverage')
    if any(c['case']!=f"schematic_receiver_{c['process']}_{c['temperature']}" for c in children):
        raise ValueError('Source DC case name differs from its PVT point')
    if not set(PILOTS)<=expected:raise ValueError('Required pilot conditions missing')
    return sorted(children,key=lambda c:(PILOTS.index((c['process'],c['temperature']))
        if (c['process'],c['temperature']) in PILOTS else len(PILOTS)+actual.index((c['process'],c['temperature']))))


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_static_matrix'):
        raise ValueError('Use the completed standard unclamped source DC matrix')
    manifest=json.loads((parent/'manifest.json').read_text())
    cases=selected_cases(manifest,json.loads((ROOT/'requirements.json').read_text()))
    children=[]
    for case in cases:
        control=(ROOT/case['root']).resolve()
        if (not control.is_relative_to(ROOT/'build/diagnostics/receiver_static_diagnosis') or
                diagnosis.digest(control/'manifest.json')!=case['manifest_sha256']):
            raise ValueError('Source DC control manifest changed')
        child=diagnosis.prepare(control)
        children.append(dict(case=case['case'],process=case['process'],temperature=case['temperature'],
            control=case['root'],root=str(child.relative_to(ROOT)),manifest_sha256=diagnosis.digest(child/'manifest.json')))
    identity=dict(parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=diagnosis.digest(parent/'manifest.json'),
        requirements_sha256=diagnosis.digest(ROOT/'requirements.json'),producer_sha256=diagnosis.digest(Path(__file__)),
        code={n:diagnosis.digest(ROOT/'scripts'/n) for n in diagnosis.CODE},children=children)
    root=ROOT/'build/diagnostics/receiver_decision_load_matrix'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    diagnosis.capture_manifest(root/'manifest.json',dict(identity=identity,qualified_phy=False))
    return root


def pilot_gate(root,children,wait_slot):
    # Recheck completed pilots through the scientific runner; never run an
    # incomplete pilot here, where its original independent owner may be live.
    for child in children[:len(PILOTS)]:
        if not (ROOT/child['root']/'summary.json').exists():
            raise ValueError('Pilot incomplete; full DC campaign remains held')
    results=[]
    for child in children[:len(PILOTS)]:
        result=diagnosis.run(ROOT/child['root'],wait_slot)
        if result['manifest_sha256']!=child['manifest_sha256'] or result['diagnostic_complete'] is not True:
            raise ValueError('Pilot report does not prove completion')
        results.append(result['stronger_pmos_load']['metrics']['passed'])
    if not all(results):raise ValueError('A static pilot failed; remaining DC simulations are held')


def run(root,wait_slot=None):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_decision_load_matrix'):
        raise ValueError('Use a prepared stronger-PMOS source DC matrix')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity'];stamp=diagnosis.digest(root/'manifest.json')
    def unchanged():
        parent=ROOT/identity['parent']
        if (diagnosis.digest(root/'manifest.json')!=stamp or diagnosis.digest(Path(__file__))!=identity['producer_sha256'] or
                diagnosis.digest(ROOT/'requirements.json')!=identity['requirements_sha256'] or
                diagnosis.digest(parent/'manifest.json')!=identity['parent_manifest_sha256'] or
                any(diagnosis.digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items())):
            raise ValueError('Source DC campaign context changed')
        cases=selected_cases(json.loads((parent/'manifest.json').read_text()),json.loads((ROOT/'requirements.json').read_text()))
        if [(c['case'],c['process'],c['temperature'],c['root']) for c in cases]!=[
                (c['case'],c['process'],c['temperature'],c['control']) for c in identity['children']]:
            raise ValueError('Source DC campaign selection changed')
        for child in identity['children']:
            path=(ROOT/child['root']).resolve()
            if (not path.is_relative_to(ROOT/'build/diagnostics/receiver_decision_load_static') or
                    diagnosis.digest(path/'manifest.json')!=child['manifest_sha256'] or
                    json.loads((path/'manifest.json').read_text())['identity']['parent']!=child['control']):
                raise ValueError('Source DC child context changed')
    results=[]
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            unchanged();pilot_gate(root,identity['children'],wait_slot);unchanged()
            for child in identity['children']:
                unchanged()
                atomic(root/'state.json',dict(status='running_full_dc',case=child['case'],completed=len(results),qualified_phy=False))
                result=diagnosis.run(ROOT/child['root'],wait_slot)
                if result['manifest_sha256']!=child['manifest_sha256'] or result['diagnostic_complete'] is not True:
                    raise ValueError('Source DC child report incomplete')
                results.append(dict(case=child['case'],passed=result['stronger_pmos_load']['metrics']['passed'],
                    report_sha256=diagnosis.digest(ROOT/child['root']/'summary.json')))
            unchanged()
            summary=dict(diagnostic_complete=True,qualified_phy=False,manifest_sha256=stamp,
                required=len(identity['children']),dc_all_passed=all(r['passed'] for r in results),results=results,
                scope='Original source DC corners only; clock, native and PHY admission still required')
            atomic(root/'summary.json',summary)
            atomic(root/'state.json',dict(status='complete',completed=len(results),qualified_phy=False))
        except Exception as error:
            atomic(root/'state.json',dict(status='held_for_diagnosis',error=str(error),completed=len(results),qualified_phy=False))
            raise
    print(root/'summary.json',flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve()),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
