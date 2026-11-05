#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recover both complete retained routed traces after NumPy Boolean JSON failure.

Read-only recovery: never retry the solver, take over the failed producer, edit
its reports/state, change gates, or treat an incomplete trace as completion.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import continue_weighted_routed_v2 as followup
import probe_weighted_routed_v2 as pilot
import verify_weighted_routed_v2 as original_verification
import weighted_routed_measurement_v3 as streaming
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT=pilot.ROOT
VERSION='retained-routed-native-complete-waveform-report-recovery-v3.1'
CONTEXT='weighted_routed_recovery_v3'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def check_failure(log,state):
    if (state.get('status')!='held_for_diagnosis' or 'probe_weighted_routed_v2.py' not in log
        or not re.search(r'TypeError: Object of type bool_? is not JSON serializable',log)):
        raise ValueError('Require the retained terminal NumPy Boolean JSON reporting failure')


def terminal_metadata(folder):
    names,w=read(folder/'bench.raw');log=(folder/'ngspice.log').read_text();console=(folder/'console.log').read_text()
    rows=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log);elapsed=re.findall(r'Total elapsed time \(seconds\)\s*=\s*([\d.eE+-]+)',log)
    if (len(rows)!=1 or int(rows[0])!=len(w) or len(elapsed)!=1 or not math.isfinite(float(elapsed[0])) or float(elapsed[0])<=0
        or re.search(r'Timestep too small|simulation\(s\) aborted|Error:',log,re.I)
        or 'Traceback' in console):raise ValueError('Require one completed native transient and retained successful runner output')
    time=w[:,names.index('time')]
    if time[0]!=0 or time[-1]<60e-9*(1-1e-8):raise ValueError('Require the whole zero-to-60ns routed trace')
    return dict(records=len(w),variables=len(names),first_time_s=float(time[0]),last_time_s=float(time[-1]),elapsed_seconds=float(elapsed[0]),numerically_complete=True)


def collect(parent,failed_followup):
    fm=followup.bound(failed_followup);failure_state=json.loads((failed_followup/'state.json').read_text())
    check_failure((failed_followup/'pilot.log').read_text(),failure_state)
    if fm['identity']['pilot']!=str(parent.relative_to(ROOT)):raise ValueError('Reporting failure belongs to another native pilot')
    m=pilot.bound(parent);i=m['identity'];text,witness,components,paths=pilot.libraries(ROOT/i['receipt'])
    if text!=(parent/'bank.spice').read_text() or witness!=i['witness'] or components!=i['components']:
        raise ValueError('Original whole-bank RC, primitive or control witness changed')
    if len(witness['devices'])!=2495 or sum(witness['primitive_counts'].values())!=2651 or len(witness['controls'])!=25:
        raise ValueError('Retained full native bank coverage changed')
    c=i['components'];gate=json.loads((parent/'control_gate.json').read_text())
    if pilot.control_gate.require(ROOT/gate['receipt'],ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])!=gate:
        raise ValueError('Matched four-case physical fine-control prerequisite changed')
    paths += [parent/n for n in ['manifest.json','state.json','bank.spice','control_gate.json']]
    paths += [failed_followup/n for n in ['manifest.json','state.json','pilot.log']]
    paths += [ROOT/n for n in i['inputs']]
    paths += [Path(__file__),Path(streaming.__file__),Path(pilot.__file__),Path(original_verification.__file__),Path(followup.__file__),Path(runner.__file__),
              ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/weighted_routed_observation_v2.py']
    metadata=[]
    for task in m['tasks']:
        folder=parent/task['id'];deck=(folder/'bench.cir').read_text();translated,_=runner.translate(deck)
        if deck!=pilot.fixture(parent,task['spec'],witness) or translated!=(folder/'bench.ngspice.cir').read_text():
            raise ValueError('Retained prepared or actual translated native deck changed')
        metadata.append(terminal_metadata(folder))
        paths += [folder/n for n in ['bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log']]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths};rows=[]
    for task,meta in zip(m['tasks'],metadata):
        folder=parent/task['id'];result=streaming.measure(folder,task['spec'],witness)
        # Plain dumps is intentional: no permissive encoder or default string
        # conversion may hide unsupported objects in the recovered schema.
        json.dumps(result)
        rows.append(dict(task=task,result=result,error=None,numerical_completion=meta))
    assessment=original_verification.assess(rows);json.dumps(assessment);pilot.bound(parent);followup.bound(failed_followup)
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Retained evidence changed during complete-waveform recovery')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),failed_followup=str(failed_followup.relative_to(ROOT)),
        measurement_version=streaming.VERSION,inputs=inputs)
    return dict(identity=identity,rows=rows,assessment=assessment,all_declared_raw_waveforms_verified=True,
        original_reporting_failure_preserved=True,original_producer_restarted=False,solver_rerun=False,
        legal_code_table_admitted=False,qualified_phy=False,electrical_qualification_passed=False,
        scope='Both original complete 60ns routed SS40 coarse0/1 traces, unchanged native circuits/limits and streamed full measurements; independent recovery of failed JSON reporting only, no dense-code/periodic/PVT/PHY admission')


def recover(parent,failed_followup):
    result=collect(parent,failed_followup);i=result['identity']
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);pilot.atomic(out/'summary.json',result);return out


def verify(out):
    retained=json.loads((out/'summary.json').read_text());i=retained['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Retained recovery identity/evidence changed')
    if collect(ROOT/i['parent'],ROOT/i['failed_followup'])!=retained:
        raise ValueError('Recovered complete native-waveform measurements changed')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--failed-followup',type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args()
    if not a.verify and a.failed_followup is None:p.error('Require --failed-followup for new recovery')
    print(verify(a.artifact.resolve()) if a.verify else recover(a.artifact.resolve(),a.failed_followup.resolve()),flush=True)
