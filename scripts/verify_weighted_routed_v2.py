#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate routed timing decks/observations and remeasure complete raw traces."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import probe_weighted_routed_v2 as pilot

ROOT=pilot.ROOT
VERSION='independent-whole-routed-weighted-bank-sparse-native-timing-v2.1'
CONTEXT='weighted_routed_verification_v2'


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete routed sparse timing matrix')
    if any([s['code'] for s in r['result']['samples']]!=pilot.CODES for r in rows):
        raise ValueError('Routed pulse/code coverage changed')
    points={r['task']['spec']['coarse']:r['result'] for r in rows}
    numerical_pulses=all(p['pulse_integrity_passed'] for p in points.values())
    result=dict(process='ss',temperature=40,coarse_choices=[0,1],codes=pilot.CODES,
        pulse_integrity_passed=numerical_pulses,
        routed_control_settling_passed=all(p['routed_control_settling_passed'] for p in points.values()),
        terminal_screen_passed=all(p['terminal_screen_passed'] for p in points.values()),
        observed_single_code_steps=[],code_zero_repetition=[],sampled_fine_order_passed=False,
        coarse0_fine31_to_coarse1_fine0_overlap_ps=None,minimum_quarter_headroom_ps=points[0]['minimum_quarter_headroom_ps'],
        code_zero_repeat_limit_ps=20,sampled_sparse_screen_passed=False,legal_code_table_admitted=False,qualified_phy=False)
    if not numerical_pulses:return result
    for coarse,point in points.items():
        samples=point['samples'];lookup={s['code']:s for s in samples[:-1]}
        for edge in ['rise','fall']:
            for a,b in [(0,1),(15,16)]:
                delta=lookup[b][edge+'_delay_ps']-lookup[a][edge+'_delay_ps']
                result['observed_single_code_steps'].append(dict(coarse=coarse,edge=edge,codes=[a,b],step_ps=delta,passed=0<delta<=20))
            delta=abs(samples[-1][edge+'_delay_ps']-samples[0][edge+'_delay_ps'])
            result['code_zero_repetition'].append(dict(coarse=coarse,edge=edge,difference_ps=delta,passed=delta<=20))
    result['sampled_fine_order_passed']=all(
        b[e+'_delay_ps']>a[e+'_delay_ps'] for p in points.values() for e in ['rise','fall']
        for a,b in zip(p['samples'][:-2],p['samples'][1:-1]))
    result['coarse0_fine31_to_coarse1_fine0_overlap_ps']={e:points[0]['samples'][-2][e+'_delay_ps']-points[1]['samples'][0][e+'_delay_ps'] for e in ['rise','fall']}
    result['sampled_sparse_screen_passed']=bool(
        result['routed_control_settling_passed'] and result['terminal_screen_passed'] and result['sampled_fine_order_passed']
        and result['minimum_quarter_headroom_ps'] is not None and result['minimum_quarter_headroom_ps']>0
        and min(result['coarse0_fine31_to_coarse1_fine0_overlap_ps'].values())>=0
        and all(s['passed'] for s in result['observed_single_code_steps'])
        and all(s['passed'] for s in result['code_zero_repetition']))
    return result


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];c=i['components'];gate=json.loads((out/'control_gate.json').read_text())
        proof=pilot.control_gate.require(ROOT/gate['receipt'],ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])
        if proof!=gate:raise ValueError('Matched physical fine-control prerequisite changed')
        text,witness,components,_=pilot.libraries(ROOT/i['receipt'])
        if text!=(out/'bank.spice').read_text() or witness!=i['witness'] or components!=c:
            raise ValueError('Actual whole-bank RC or native control/MOS observations cannot be regenerated')
        state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if (state['status']!='weighted_routed_pilot_complete' or state['errors'] or state['cases']!=len(m['tasks'])
            or len(aggregate)!=len(m['tasks'])):raise ValueError('Require all declared numerical-error-free routed cases')
        paths=[out/n for n in ['manifest.json','state.json','summary.json','control_gate.json',*m['libraries']]];rows=[]
        for task,retained in zip(m['tasks'],aggregate):
            folder=out/task['id'];r=json.loads((folder/'summary.json').read_text())
            if (r!=retained or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,task['spec'],witness)
                or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
                or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):
                raise ValueError('Routed task/raw/deck evidence changed')
            measured=pilot.measure(folder,task['spec'],witness)
            if measured!=r['result']:raise ValueError('Actual routed native waveform remeasurement changed')
            rows.append(dict(task=task,result=measured));paths += [folder/n for n in ['summary.json',*r['files']]]
        assessment=assess(rows);pilot.bound(out)
        if pilot.control_gate.require(ROOT/gate['receipt'],ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])!=proof:
            raise ValueError('Fine-control prerequisite changed during waveform verification')
        paths += [ROOT/gate['receipt']/'summary.json',Path(__file__),Path(pilot.__file__),Path(pilot.observation.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths})
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Routed evidence changed during verification')
        receipt=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False)
        pilot.atomic(receipt/'summary.json',dict(identity=identity,assessment=assessment,all_declared_raw_waveforms_verified=True,
            qualified_phy=False,legal_code_table_admitted=False,
            scope='Complete routed 16-choice bank, SS40 coarse0/1 sparse pulse/LSB/carry/repeat screen only; no dense code, periodic clock, all-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
