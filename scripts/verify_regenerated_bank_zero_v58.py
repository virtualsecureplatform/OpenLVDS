#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure complete branch-regeneration component-RC feasibility."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import probe_regenerated_bank_v56 as producer

sha=producer.common.sha

ROOT=producer.ROOT
VERSION='independent-complete-regenerated-component-zero-native-waveform-v58.1'
CONTEXT='regenerated_bank_zero_verification_v58'


def verify(parent):
    m=producer.bound(parent);i=m['identity']
    state=json.loads((parent/'state.json').read_text())
    if state!=dict(status='complete',cases=1,errors=0,qualified_phy=False):raise ValueError('Require one complete successful solver task')
    r=json.loads((parent/'summary.json').read_text());row=json.loads((parent/'0/summary.json').read_text())
    if (r['rows']!=[row] or row['error'] is not None or row['spec']!=i['spec']
            or any(sha(parent/'0'/n)!=h for n,h in row['files'].items())):
        raise ValueError('Original complete component-RC waveform evidence changed')
    paths=[parent/'manifest.json',parent/'state.json',parent/'summary.json',parent/'0/summary.json',
           *[parent/'0'/n for n in row['files']],*[ROOT/n for n in i['inputs']],Path(__file__),Path(producer.__file__)]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True);producer.common.baseline.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    measured=producer.measure(parent,i)
    if measured!=row['result']:raise ValueError('Complete component-RC waveform does not remeasure exactly')
    # Deliberately observe a clock-data node as a supposedly static control.
    # The full waveform checker must catch its movement; no source data changes.
    wrong=deepcopy(i);wrong['observations']['controls'][0]['node']='IN'
    bad_control=producer.measure(parent,wrong)
    if bad_control['control_settling_passed']:raise ValueError('Clock-data substitution was accepted as a settled control')
    wrong=deepcopy(i)
    for d in wrong['observations']['devices']:d['limit_v']=.1
    bad_voltage=producer.measure(parent,wrong)
    if bad_voltage['terminal_screen_passed']:raise ValueError('Incorrect native voltage limits were accepted')
    producer.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Waveform inputs changed during remeasurement')
    result=dict(result=measured,all_complete_waveforms_consumed=True,all_declared_cases_consumed=True,
                negative_controls=[dict(fault='clock_data_as_static_control',rejected=True),dict(fault='wrong_native_voltage_limit',rejected=True)],
                full_native_waveform_remeasured=True,component_rc_zero_screen_passed=measured['component_rc_zero_screen_passed'],
                electrical_qualification_passed=False,qualified_phy=False,
                scope='Independent complete SS40 component-RC zero waveform/terminal/control/repeatability gate only; no new wire RC, sparse/dense/periodic/all-PVT or PHY admission')
    result['files']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    producer.common.baseline.atomic(out/'summary.json',result);bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items())
            or not r['full_native_waveform_remeasured'] or not r['all_declared_cases_consumed']
            or len(r['negative_controls'])!=2 or not all(c['rejected'] for c in r['negative_controls'])
            or r['component_rc_zero_screen_passed']!=r['result']['component_rc_zero_screen_passed']
            or r['qualified_phy'] or r['electrical_qualification_passed']):raise ValueError('Independent component-RC zero receipt changed')
    producer.bound(ROOT/i['parent']);return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path)
    print(verify(p.parse_args().parent.resolve()),flush=True)
