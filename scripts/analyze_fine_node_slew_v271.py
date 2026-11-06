#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure loaded fine-node slew from the complete bound stage-latency traces."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import analyze_isolated_stage_latency_v262 as source
from native_binary_raw_v2 import read
from regenerated_bank_periodic_measure_v67 import crossings
from probe_digital_dcc_v2 import atomic

ROOT=source.ROOT
sha=source.sha
VERSION='completed-isolated-bank-fine-node-full-swing-slew-v271.1'
CONTEXT='fine_node_slew_v271'


def measure(t,voltage):
    edges={}
    for up,name in ((True,'rise'),(False,'fall')):
        low=crossings(t,voltage,.18,up);mid=crossings(t,voltage,.9,up);high=crossings(t,voltage,1.62,up)
        if len(low)!=8 or len(mid)!=8 or len(high)!=8:raise ValueError('Require eight complete full-swing edges per polarity')
        if not all(a<b<c if up else c<b<a for a,b,c in zip(low,mid,high)):
            raise ValueError('Native 10/50/90 percent crossings are not ordered')
        values=[abs(b-a) for a,b in zip(low,high)]
        if not all(np.isfinite(v) and v>0 for v in values):raise ValueError('Nonfinite or invalid native slew')
        edges[name]=dict(slews_10_90_ps=values,minimum_ps=min(values),maximum_ps=max(values))
    maximum=max(v['maximum_ps'] for v in edges.values())
    return dict(edges=edges,maximum_slew_ps=maximum,within_current_250ps_output_domain=maximum<=250)


def run(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (parent.parent!=ROOT/'build/diagnostics'/source.CONTEXT or i['version']!=source.VERSION
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or r.get('analysis_completed') is not True or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Require unchanged complete native stage-latency receipt')
    rows=[]
    for row in r['rows']:
        case=ROOT/row['case']
        if source.analyze(case)!=row:raise ValueError('Original complete native stage evidence does not reproduce')
        names,w=read(case/'bench.raw');t=w[:,names.index('time')]*1e12
        fine=measure(t,w[:,names.index('v(xd.fine_node)')]);out=measure(t,w[:,names.index('v(out)')])
        original=json.loads((case/'summary.json').read_text())['result']['maximum_output_slew_ps']
        if abs(out['maximum_slew_ps']-original)>1e-6:raise ValueError('Original complete output-slew metric does not reproduce')
        rows.append(dict(case=row['case'],task=row['task'],fine_node=fine,output=out,all_eight_full_swing_edges_observed=True,
                         direct_output_variant_tested=False,qualified_phy=False))
    paths=[Path(__file__),Path(source.__file__),parent/'manifest.json',parent/'summary.json',parent/'state.json',
           Path(read.__code__.co_filename),Path(crossings.__code__.co_filename),Path(atomic.__code__.co_filename)]
    inputs={**i['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Native fine-node evidence changed during analysis')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs=inputs,numpy=np.__version__)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'summary.json',dict(rows=rows,analysis_completed=True,parameters_changed=False,electrical_qualification_passed=False,qualified_phy=False,
        scope='Observed internal/output slew on complete original traces only; removing or changing the regenerator alters loading and requires new native replay, no bypass timing or PHY admission'))
    atomic(out/'state.json',dict(status='complete',analysis_completed=True,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('receipt',type=Path);a=p.parse_args();print(run(a.receipt.resolve()),flush=True)
