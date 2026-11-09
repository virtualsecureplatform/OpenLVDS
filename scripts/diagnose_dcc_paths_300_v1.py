#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind complete corrected-source native cases to startup-inclusive path analysis."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_dcc_inputs_300_v2 as producer
import dcc_path_timing_300_v1 as paths
from native_binary_raw_v2 import validate
from replay_bank_300_v2 import same

ROOT=producer.ROOT
VERSION='corrected-source-native-dcc-path-decomposition-300-v1'
CONTEXT='dcc_path_diagnostic_300_v1'


def run(parent,cases):
    if not cases or len(cases)!=len(set(cases)):raise ValueError('Require unique completed native case IDs')
    for number in cases:
        if not (parent/number/'summary.json').is_file():raise ValueError('Native source case is still pending')
    m=producer.bound(parent);rows=[];inputs=dict(m['identity']['inputs'])
    def retain(p):inputs[str(p)]=producer.sha(p)
    retain(parent/'manifest.json')
    for number in cases:
        task=next((t for t in m['tasks'] if t['id']==number),None)
        if task is None:raise ValueError('Undeclared corrected source case')
        folder=parent/number;row=json.loads((folder/'summary.json').read_text())
        if row['task']!=task or row['error'] is not None or not isinstance(row['result'],dict) or not same(row['result'],row['independent_result']):
            raise ValueError('Require a complete independently reproduced native source result')
        for n,h in row['files'].items():
            if Path(n).name!=n or producer.sha(folder/n)!=h:raise ValueError('Completed source witness changed')
            retain(folder/n)
        retain(folder/'summary.json');rows.append(row)
    for mod in list(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=cases,inputs=inputs)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False));measured=[]
    try:
        for row in rows:
            task=row['task'];s=task['spec'];folder=parent/task['id']
            names,w=validate(folder/'bench.raw',{'v(xd.qt)'},producer.waveform.capture_stop_ps(s)*1e-12)
            original=producer.metrology.measure(names,w,s)
            independent=producer.metrology.measure(names,w,s,independent=True)
            if original!=row['result'] or not same(original,independent):raise ValueError('Original complete source metrics do not reproduce')
            a=paths.measure(names,w,s);b=paths.measure(names,w,s,independent=True)
            if not same(a,b):raise ValueError('Independent source path timing does not reproduce')
            measured.append(dict(task=task,original_source_screen_passed=original['source_screen_passed'],
                all_original_metrics_reproduced=True,independent_path_metrics_reproduced=True,path=a))
        if any(producer.sha(Path(n))!=h for n,h in inputs.items()):raise ValueError('Source path inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(rows=measured,timing_modified=False,source_matrix_admitted=False,
            physical_source_admitted=False,qualified_phy=False,scope='Explicit source timing diagnosis only; original failures retained'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('cases',nargs='+')
    a=p.parse_args();print(run(a.parent.resolve(),a.cases),flush=True)
