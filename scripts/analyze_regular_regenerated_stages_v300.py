#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Decompose complete native regular-pair crossings and first/last history changes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import probe_regular_regenerated_bank_v263 as source
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings

ROOT=source.ROOT
sha=source.sha
VERSION='completed-regular-pair-four-stage-native-history-diagnosis-v300.1'
CONTEXT='regular_regenerated_stages_v300'
NODES=('input','selected','fine_node','restored_b','output')
INVERTED={'selected','restored_b'}
STAGES=('input_to_selected','selected_to_fine_node','fine_node_to_restored_b','restored_b_to_output')


def decompose(t,signals,reference):
    if (set(signals)!=set(NODES) or len(t)<2 or not np.isfinite(t).all() or t[0]<0 or t[0]>1e-6 or np.any(np.diff(t)<=0)
        or any(len(signals[n])!=len(t) or not np.isfinite(signals[n]).all() for n in NODES)):
        raise ValueError('Require finite complete-startup time and all five native nodes')
    if any(not (signals[n][0]>.9 if n in INVERTED else signals[n][0]<.9) for n in NODES):
        raise ValueError('Initial native polarity does not establish the expected crossing epoch')
    result={}
    for up,edge in ((True,'rise'),(False,'fall')):
        events={n:crossings(t,signals[n],.9,not up if n in INVERTED else up) for n in NODES}
        if any(len(v)!=8 for v in events.values()) or len(reference.get(edge,[]))!=8:
            raise ValueError('Require all eight matched crossings at every native stage')
        total=[b-a for a,b in zip(events['input'],events['output'])]
        if any(not np.isfinite(v) or v<=0 for v in reference[edge]) or max(abs(a-b) for a,b in zip(total,reference[edge]))>1e-6:
            raise ValueError('Crossings do not reproduce recorded complete native delays')
        parts={stage:[b-a for a,b in zip(events[NODES[k]],events[NODES[k+1]])] for k,stage in enumerate(STAGES)}
        residual=max(abs(sum(parts[stage][k] for stage in STAGES)-total[k]) for k in range(8))
        history={stage:parts[stage][0]-parts[stage][-1] for stage in STAGES}
        history_residual=abs(sum(history.values())-(total[0]-total[-1]))
        if residual>1e-6 or history_residual>1e-6:raise ValueError('Native stage/history decomposition does not telescope')
        result[edge]=dict(crossing_times_ps=events,stage_delays_ps=parts,total_delays_ps=total,
            stage_ranges_ps={stage:dict(minimum=min(v),maximum=max(v),span=max(v)-min(v)) for stage,v in parts.items()},
            first_minus_last_stage_ps=history,first_minus_last_total_ps=total[0]-total[-1],
            maximum_sum_residual_ps=residual,history_sum_residual_ps=history_residual)
    return result


def analyze(folder):
    parent=folder.parent;m=source.bound(parent);i=m['identity'];row=json.loads((folder/'summary.json').read_text());task=row['task']
    if (task not in m['tasks'] or task['id']!=folder.name or row['spec']!=task['spec'] or row['error'] is not None or row['result'] is None
        or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
        or any(sha(folder/n)!=h for n,h in row['files'].items()) or sha(folder/'bench.cir')!=task['deck_sha256']):
        raise ValueError('Require explicit complete unchanged regular-pair native case')
    measured=source.measure(folder,i,task['spec'])
    if measured!=row['result']:raise ValueError('Original full native metrics do not reproduce')
    names=dict(input='v(in)',selected='v(xd.selected)',fine_node='v(xd.fine_node)',restored_b='v(xd.restored_b)',output='v(out)')
    columns,w=validate(folder/'bench.raw',set(names.values()),25e-9);t=w[:,columns.index('time')]*1e12
    signals={n:w[:,columns.index(column)] for n,column in names.items()};parts=decompose(t,signals,measured['edge_delays_ps'])
    paths=[parent/'manifest.json',parent/'bank.spice',folder/'summary.json',*[folder/n for n in row['files']]]
    return dict(case=str(folder.relative_to(ROOT)),task=task,native_mos=len(i['observations']['devices']),
        programming_gates=len(i['observations']['programming_gates']),all_original_native_metrics_reproduced=True,
        recorded_gates={k:v for k,v in measured.items() if k.endswith('_passed')},decomposition=parts,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})


def run(cases):
    if not cases or len(set(cases))!=len(cases):raise ValueError('Require explicit unique completed cases')
    rows=[analyze(folder) for folder in cases];inputs={n:h for row in rows for n,h in row['inputs'].items()}
    files=sorted({Path(module.__file__).resolve() for module in list(sys.modules.values()) if getattr(module,'__file__',None)
        and Path(module.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in files})
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Native stage evidence changed during analysis')
    identity=dict(version=VERSION,cases=[str(p.relative_to(ROOT)) for p in cases],inputs=inputs,numpy=np.__version__,byteorder=sys.byteorder)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(rows=rows,analysis_completed=True,parameters_changed=False,
        shared_wire_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False,
        scope='Complete component-trace signed 0.9V crossing/history differences only; not intrinsic delay, another-code prediction, routed-bank/PVT/DLL/PHY admission'),indent=2)+'\n')
    (out/'state.json').write_text('{"status":"complete","analysis_completed":true,"qualified_phy":false}\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',nargs='+',type=Path);a=p.parse_args();print(run([folder.resolve() for folder in a.cases]))
