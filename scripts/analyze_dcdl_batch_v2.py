#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure immutable dense traces with explicit digital-control margins.

The producer mistakenly imposed a 10 mV reference tolerance on a native
inverter output. Keep that report. This consumer checks ideal stimulus inputs
at 10 mV, internal logic outputs at 10/90% rail margins and every custom MOS
terminal pair at 1.95 V. It neither reruns a solver nor edits producer evidence.
"""
import argparse
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
import probe_digital_dcdl_batch_v2 as producer
import verify_digital_clocking_v2 as binary

h=producer.h
ROOT=h.ROOT
VERSION='dense-dcdl-digital-control-reanalysis-v2.1'
RECOVERABLE='Fine control changed during a tagged pulse'


def measure(folder,task):
    names,w=h.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    codes=task['spec']['codes']
    if not np.isfinite(w).all() or t[-1]<len(codes)*10000-.01:raise ValueError('Incomplete dense trace')
    def get(n):
        if n=='VSS':return np.zeros(len(t))
        if n=='VDD':return w[:,names.index('v(vdd)')]
        node=('xd.'+n) if n in ('r0','f0') or n.startswith('cap') else n.lower()
        return w[:,names.index('v('+node+')')]
    samples=[];controls=[]
    for i,code in enumerate(codes):
        base=i*10000;window=(t>=base)&(t<=base+10000)
        sample=dict(code=code)
        for rising,label in [(True,'rise'),(False,'fall')]:
            a=h.crossings(t[window],get('IN')[window],rising)
            b=h.crossings(t[window],get('OUT')[window],rising)
            if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra pulse or wrong epoch')
            sample[label+'_delay_ps']=float(b[0]-a[0])
        stable=(t>=base+1500)&(t<base+9500)
        worst_input=worst_logic=0.
        for bit in range(31):
            target=1.8 if bit<code else 0
            a=float(np.max(np.abs(get(f'E{bit}')[stable]-target)))
            b=float(np.max(np.abs(get(f'EB{bit}')[stable]-(1.8-target))))
            worst_input=max(worst_input,a);worst_logic=max(worst_logic,b)
        if worst_input>.01:raise ValueError('Unstable digital control stimulus')
        if worst_logic>.18:raise ValueError('Internal control violates 10/90% logic margins')
        controls.append(dict(code=code,stimulus_max_deviation_v=worst_input,internal_max_deviation_v=worst_logic,
                             stimulus_limit_v=.01,internal_logic_limit_v=.18))
        samples.append(sample)
    stress=[]
    for device in task['devices']:
        voltages=[get(n) for n in device['terminals']]
        maximum=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(voltages,2))
        stress.append(dict(device=device['name'],max_terminal_difference_v=maximum,limit_v=1.95,passed=maximum<=1.95))
    return dict(version=VERSION,samples=samples,controls=controls,custom_mos_stress=stress,
        custom_mos_stress_passed=all(d['passed'] for d in stress),qualified_phy=False,
        legal_code_table_admitted=False,scope='Source delay samples and digital control/stress reanalysis only')


def case(out,case_id):
    m=producer.bound(out)
    task=next((t for t in m['tasks'] if t['id']==case_id),None)
    if task is None:raise ValueError('Unknown dense case')
    folder=out/case_id;row=json.loads((folder/'summary.json').read_text())
    if row['task']!=task or row['error'] not in (None,RECOVERABLE):
        raise ValueError('Case is not a completed, recoverable measurement')
    if not binary.REQUIRED<=set(row['files']) or any(h.sha(folder/n)!=v for n,v in row['files'].items()):
        raise ValueError('Missing or changed dense case output')
    stamp=h.sha(folder/'summary.json');binary.export_matches_raw(folder)
    result=measure(folder,task)
    if stamp!=h.sha(folder/'summary.json') or any(h.sha(folder/n)!=v for n,v in row['files'].items()):
        raise ValueError('Dense source changed during reanalysis')
    return dict(task=task,result=result,retained_producer_error=row['error'],
        producer_summary_sha256=stamp,files=row['files'])


def verify(out,case_id=None):
    if case_id is not None:
        # A producer atomically writes the case summary only after export/hash
        # completion and never revisits it. Check exact bytes before and after;
        # other cases may continue without taking the campaign's execution lock.
        rows=[case(out,case_id)]
    else:
        with (out/'.execution.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            m=producer.bound(out);state=json.loads((out/'state.json').read_text())
            if state['status']!='source_screen_complete' or state['cases']!=len(m['tasks']):
                raise ValueError('Dense producer is not terminal')
            rows=[case(out,t['id']) for t in m['tasks']]
    identity=dict(version=VERSION,artifact=str(out.relative_to(ROOT)),manifest_sha256=h.sha(out/'manifest.json'),
        case_id=case_id,inputs={r['task']['id']:r['producer_summary_sha256'] for r in rows},
        code={str(p.relative_to(ROOT)):h.sha(p) for p in [Path(__file__),Path(binary.__file__),Path(producer.__file__)]})
    receipt=ROOT/'build/diagnostics/dcdl_batch_reanalysis_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    result=dict(identity=identity,rows=rows,qualified_phy=False,legal_code_table_admitted=False,
        scope='Reanalysis preserves the original measurement failure; no native physical or PHY admission')
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior receipt changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--case');a=p.parse_args()
    print(verify(a.artifact.resolve(),a.case),flush=True)
