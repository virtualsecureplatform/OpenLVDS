#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare original/settled reassertion windows without changing any native gate."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
import counter_pvt_300_v1 as producer
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import crossings
ROOT=producer.ROOT
VERSION='fresh-counter-reassertion-window-diagnosis-300-v1'


def windows(t,signals,reassert_ps=32000):
    if t[0]>1e-6 or t[-1]<39999 or np.any(np.diff(t)<=0):raise ValueError('Require complete startup and 40 ns')
    intervals={'clear_before_reassert':(30000,31500),'reassert_transition':(reassert_ps-10,reassert_ps+1000),
               'original_new_checker':(30000,40001),'legacy_relative_settled_window':(reassert_ps+1000,40001)}
    rows={}
    for node,values in signals.items():
        if len(values)!=len(t) or not np.isfinite(values).all():raise ValueError('Invalid native diagnosis signal')
        row={}
        for name,(a,b) in intervals.items():
            indices=np.flatnonzero((t>=a)&(t<b))
            if len(indices)<2:raise ValueError('Missing reassertion observation interval')
            peak=indices[np.argmax(abs(values[indices]))]
            row[name]=dict(maximum_absolute_voltage_v=float(abs(values[peak])),
                peak_voltage_v=float(values[peak]),peak_time_ps=float(t[peak]),
                below_original_180mv_limit=bool(np.max(abs(values[indices]))<=.18))
        row['rising_50_percent_events_after_reassert_ps']=crossings(t,values)[crossings(t,values)>reassert_ps].tolist()
        rows[node]=row
    return dict(nodes=rows,window_comparison_only=True,original_gate_not_modified=True,qualified_phy=False)


def run(parent,number):
    m=producer.bound(parent,full=False);folder=parent/number
    task=next(t for t in m['tasks'] if t['id']==number)
    row=json.loads((folder/'summary.json').read_text())
    if row['task']!=task or row['error'] is not None:raise ValueError('Require completed original native case')
    inputs={**m['identity']['guards'],**m['identity']['pdk_files'],**m['identity']['external_files']}
    for name,digest in row['files'].items():
        if producer.sha(folder/name)!=digest:raise ValueError('Completed native case changed')
        inputs[str((folder/name).relative_to(ROOT))]=digest
    for path in (parent/'manifest.json',folder/'summary.json',parent/'cells.spice',parent/'pair.spice'):
        inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    inputs.update({str(Path(mod.__file__).resolve().relative_to(ROOT)):producer.sha(Path(mod.__file__).resolve())
        for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case=number,inputs=inputs)
    out=ROOT/'build/diagnostics/counter_reassertion_diagnosis_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        result=producer.protocol.measure(folder,m['identity'],task['spec'])
        result['scope']=producer.SCOPE
        if result!=row['result']:raise ValueError('Original full counter metrology no longer reproduces')
        nodes=('CLK','REQUEST','PREPARE','RESET_N','XD:XR:low0','XD:XR:high1','XD:XR:low1','XD:XR:armed')
        column=lambda n:'v('+n.replace(':','.').lower()+')'
        names,w=validate(folder/'bench.raw',{column(n) for n in nodes},40e-9)
        t=w[:,names.index('time')]*1e12
        report=windows(t,{n:w[:,names.index(column(n))] for n in nodes})
        report.update(original_metrics_reproduced=True,original_task=task,
            original_recorded_gates={k:v for k,v in result.items() if k.endswith('_passed')})
        if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Native diagnosis context changed')
        producer.atomic(out/'summary.json',report);producer.atomic(out/'state.json',dict(status='complete',qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('case');a=p.parse_args()
    print(run(a.artifact.resolve(),a.case),flush=True)
