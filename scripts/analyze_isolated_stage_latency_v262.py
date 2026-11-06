#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Decompose completed isolated-bank 0.9 V crossings without changing traces."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings

ROOT=Path(__file__).resolve().parents[1]
VERSION='completed-isolated-bank-stage-crossing-latency-v262.1'
CONTEXT='isolated_bank_stage_latency_v262'
VERSIONS={
 'strong-native-fine-isolation-after-inv1-pulse-loss-v190.1':'strong_isolated_fine_bank_v190',
 'balanced-native-driver-measured-bank-full-observation-v201.1':'balanced_isolated_fine_bank_v201',
 'strong-discharge-native-driver-measured-bank-full-observation-v220.1':'discharge_isolated_fine_bank_v220',
}
STAGES=('input_to_selected','selected_to_fine_node','fine_node_to_out')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def decompose(t,signals,reference,count=8):
    result={}
    for up,edge in ((True,'rise'),(False,'fall')):
        events=[crossings(t,signals[n],.9,not up if n=='selected' else up) for n in ('input','selected','fine_node','output')]
        if any(len(v)!=count for v in events):raise ValueError('Require all eight matched input, selected, fine-node and output crossings')
        measured=[events[3][k]-events[0][k] for k in range(count)];expected=reference[edge]
        if len(expected)!=count or any(not np.isfinite(v) for row in events for v in row):raise ValueError('Incomplete/nonfinite native crossing history')
        agreement=max(abs(a-b) for a,b in zip(measured,expected))
        if agreement>1e-6:raise ValueError('Stage crossings do not reproduce recorded complete native delays')
        parts={name:[events[k+1][j]-events[k][j] for j in range(count)] for k,name in enumerate(STAGES)}
        residual=max(abs(sum(parts[n][k] for n in STAGES)-measured[k]) for k in range(count))
        if residual>1e-6:raise ValueError('Stage decomposition does not telescope to the original delay')
        result[edge]=dict(crossing_times_ps={n:v for n,v in zip(('input','selected','fine_node','output'),events)},
            stage_delays_ps=parts,stage_ranges_ps={n:dict(minimum=min(v),maximum=max(v)) for n,v in parts.items()},
            total_delays_ps=measured,recorded_delay_agreement_ps=agreement,maximum_sum_residual_ps=residual)
    return result


def analyze(folder):
    parent=folder.parent;m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((folder/'summary.json').read_text());task=r['task']
    if (i['version'] not in VERSIONS or parent.parent!=ROOT/'build/diagnostics'/VERSIONS[i['version']]
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or task not in m['tasks'] or task['id']!=folder.name or r['spec']!=task['spec'] or r['error'] is not None or r['result'] is None
        or task['spec']['cycles']!=8 or task['spec']['stop_ns']!=25):raise ValueError('Require explicit completed native isolated-bank case')
    if any(sha(folder/n)!=h for n,h in r['files'].items()) or sha(folder/'bench.cir')!=task['deck_sha256']:
        raise ValueError('Completed native case outputs or deck changed')
    libraries={parent/name/'bank.spice':digest for name,digest in m['libraries'].items()}
    if any(sha(p)!=h for p,h in libraries.items()):raise ValueError('Native isolated component library changed')
    spec=task['spec'];key=spec['driver']+'_c'+str(spec['fine_copies']);obs=i['observations'][key]
    names={'input':'v(in)','selected':'v(xd.selected)','fine_node':'v(xd.fine_node)','output':'v(out)'}
    required=set(names.values())|{'v('+n.replace(':','.').lower()+')' for d in obs['devices'] for n in d['terminals'] if n!='0'}
    columns,w=validate(folder/'bench.raw',required,25e-9);t=w[:,columns.index('time')]*1e12
    signals={key:w[:,columns.index(name)] for key,name in names.items()};parts=decompose(t,signals,r['result']['edge_delays_ps'])
    paths=[parent/'manifest.json',folder/'summary.json',*[folder/n for n in r['files']],*libraries]
    return dict(case=str(folder.relative_to(ROOT)),task=task,source_version=i['version'],native_mos=len(obs['devices']),
        recorded_gates={k:v for k,v in r['result'].items() if k.endswith('_passed') or k=='zero_code_fast_quarter_headroom_ps'},
        decomposition=parts,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})


def run(cases):
    if not cases or len(set(cases))!=len(cases):raise ValueError('Require explicit unique completed cases')
    rows=[analyze(p) for p in cases];inputs={n:h for r in rows for n,h in r['inputs'].items()}
    paths=[Path(__file__),Path(validate.__code__.co_filename),Path(crossings.__code__.co_filename)]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    identity=dict(version=VERSION,cases=[str(p.relative_to(ROOT)) for p in cases],inputs=inputs,numpy=np.__version__,byteorder=sys.byteorder)
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Completed native stage evidence changed during analysis')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    report=dict(rows=rows,analysis_completed=True,parameters_changed=False,electrical_qualification_passed=False,qualified_phy=False,
        scope='Read-only complete component-trace 0.9V crossing differences; signed stage differences are not intrinsic delay or a prediction for another circuit, no new timing/PVT/PHY admission')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","analysis_completed":true,"qualified_phy":false}\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',nargs='+',type=Path);a=p.parse_args();print(run([p.resolve() for p in a.cases]),flush=True)
