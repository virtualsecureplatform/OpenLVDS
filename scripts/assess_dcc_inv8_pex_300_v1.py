#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recompute complete PEX metrics and certify full/reduced pilot equivalence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import probe_dcc_inv8_pex_300_v3 as pilot
from native_binary_raw_v2 import validate
from replay_bank_300_v2 import same
from qualify_dcc_xyce_300_v1 import crossing_times,save
from xyce_profile_300 import ROOT,sha


def assess(artifact):
    state=json.loads((artifact/'state.json').read_text())
    if state.get('status')!='complete':
        raise ValueError('Refuse running/partial PEX producer')
    m=pilot.bound(artifact)
    summary=json.loads((artifact/'summary.json').read_text())
    if len(summary['rows'])!=len(m['tasks']) or len(m['tasks'])!=5:
        raise ValueError('Incomplete extracted coverage')
    inputs={str(Path(__file__).resolve()):sha(__file__),str(Path(pilot.__file__).resolve()):sha(pilot.__file__)}
    rows=[]
    for row,task in zip(summary['rows'],m['tasks']):
        if row['task']!=task or row.get('error') is not None or row.get('complete') is not True:
            raise ValueError('Require all complete successful native traces')
        folder=artifact/task['id']
        for name,digest in row['files'].items():
            if Path(name).name!=name or sha(folder/name)!=digest:
                raise ValueError('Captured output changed')
        ns,w=validate(folder/'bench.raw',set(),task['stop'])
        first,second=pilot.measure(ns,w,task),pilot.measure(ns,w,task,True)
        if not same(first,second) or not same(first,row['result']):
            raise ValueError('Independent native health replay differs')
        rows.append(dict(case=task['id'],kind=task['kind'],spec=task['spec'],
                         half_cycle_error_ps=first['source']['mean_half_cycle_error_ps'],
                         timing_passed=first['source']['timing_passed'],
                         native_terminal_stress_passed=first['native_terminal_stress_passed'],
                         maximum_terminal_span_v=max(d['maximum_terminal_span_v'] for d in first['terminal_stress'])))
        inputs[str(folder/'summary.json')]=sha(folder/'summary.json')
        inputs[str(folder/'bench.raw')]=sha(folder/'bench.raw')
    comparisons=[]
    for index in [0,1]:
        full=next(t for t in m['tasks'] if t['spec_index']==index and t['kind']=='full')
        reduced=next(t for t in m['tasks'] if t['spec_index']==index and t['kind']=='reduced')
        ns,a=validate(artifact/full['id']/'bench.raw',set(),full['stop'])
        names,b=validate(artifact/reduced['id']/'bench.raw',set(),reduced['stop'])
        if set(ns)!=set(names):raise ValueError('Different saved native terminal sets')
        edges=[];matched=True
        for node in ['p0','p180','q']:
            for up in [True,False]:
                x,y=crossing_times(ns,a,node,up),crossing_times(names,b,node,up)
                matched &= len(x)==len(y)==18
                if len(x)==len(y):edges.extend(abs(x-y)*1e12)
        dc=max(abs(float(a[0,ns.index(n)]-b[0,names.index(n)])) for n in ns if n!='time')
        final=max(abs(float(a[-1,ns.index(n)]-b[-1,names.index(n)])) for n in ns if n!='time')
        maximum=float(max(edges)) if edges else None
        comparisons.append(dict(spec_index=index,all_events_matched=bool(matched),maximum_edge_difference_ps=maximum,
                                maximum_dc_difference_v=dc,maximum_final_difference_v=final,
                                passed=bool(matched and maximum<=1 and dc<=.001 and final<=.001)))
    for name in ['manifest.json','summary.json','state.json']:
        inputs[str(artifact/name)]=sha(artifact/name)
    identity=dict(version='assess-dcc-inv8-pex-300-v1',inputs=inputs,artifact=str(artifact.relative_to(ROOT)))
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/reports/dcc_inv8_pex_assessment_300_v1'/key
    out.mkdir(parents=True,exist_ok=False)
    save(out/'summary.json',dict(identity=identity,rows=rows,full_reduced_equivalence=comparisons,
                                all_rc_comparisons_passed=all(c['passed'] for c in comparisons),
                                all_diagnostic_points_passed=all(r['timing_passed'] and r['native_terminal_stress_passed'] for r in rows),
                                qualified_phy=False))
    print(out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();assess(a.artifact.resolve())
