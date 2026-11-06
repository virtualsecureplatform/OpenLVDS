#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure completed fast-clear native counter cases."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import probe_fast_clear_counter_shared_rc_v269 as source
from diagnose_strong_counter_clear_v266 import clear_metrics
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import atomic,crossings

ROOT=source.ROOT
sha=source.sha
VERSION='completed-fast-clear-counter-native-stopped-clear-diagnosis-v299.1'
CONTEXT='fast_clear_counter_clear_diagnosis_v299'
MONITORS=('RCLK','CLK','REQUEST','PREPARE','RESET_N','XD:XR:request_i',
          'XD:XR:low0','XD:XR:high1','XD:XR:low1','XD:XR:armed')
NETS=('high1_sn','high1_qb','high2_sn','high2_qb','release_sn','release_qb')


def analyze(folder):
    parent=folder.parent;m=source.bound(parent);i=m['identity'];r=json.loads((folder/'summary.json').read_text());task=r['task']
    if (task not in m['tasks'] or task['id']!=folder.name or r['error'] is not None or r['result'] is None
        or not {'bench.cir','bench.raw','bench.ngspice.cir','ngspice.log','console.log'}<=set(r['files'])
        or any(sha(folder/n)!=h for n,h in r['files'].items()) or sha(folder/'bench.cir')!=task['deck_sha256']):
        raise ValueError('Require explicit complete unchanged fast-clear native counter case')
    measured=source.baseline.measure(folder,task['spec'],i['devices'])
    if any(r['result'].get(k)!=v for k,v in measured.items() if k!='scope'):
        raise ValueError('Original full native counter metrics do not reproduce')
    column=lambda node:'v('+node.replace(':','.').lower()+')'
    requested={column(n) for n in MONITORS}|{column(n) for d in i['devices'] for n in d['terminals'] if n!='0'}
    names,w=validate(folder/'bench.raw',requested,26e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
    signals={n:w[:,idx[column(n)]] for n in MONITORS};metrics=clear_metrics(t,signals)
    if metrics['original_async_clear_gate_reproduced']!=measured['stopped_clock_clear_and_reassert_passed']:
        raise ValueError('Detailed clear diagnosis does not reproduce the original gate')
    events={n:dict(rise_ps=crossings(t,v).tolist(),fall_ps=crossings(t,v,False).tolist(),
        final_minimum_v=float(np.min(v[t>=24000])),final_maximum_v=float(np.max(v[t>=24000]))) for n,v in signals.items()}
    # Observe actual distributed native gate nodes, rather than an invented
    # equipotential net or a private node inferred from ideal component logic.
    internal={}
    for net in NETS:
        nodes=sorted({n for d in i['devices'] for n in d['terminals'] if n=='XD:XR:'+net or n.startswith('XD:XR:'+net+'.')})
        if not nodes:raise ValueError('Missing actual distributed native phase input observations')
        internal[net]={n:dict(rise_after_request_drop_ps=[float(v) for v in crossings(t,w[:,idx[column(n)]]) if v>metrics['external_request_drop_ps']],
            fall_after_request_drop_ps=[float(v) for v in crossings(t,w[:,idx[column(n)]],False) if v>metrics['external_request_drop_ps']]) for n in nodes}
    paths=[parent/n for n in ('manifest.json','cells.spice','pair.spice')]+[folder/'summary.json',*[folder/n for n in r['files']]]
    return dict(case=str(folder.relative_to(ROOT)),task=task,clear=metrics,events=events,distributed_phase_input_events=internal,
        original_metrics_reproduced=True,native_mos_observed=len(i['devices']),terminal_screen_passed=measured['terminal_screen_passed'],
        maximum_terminal_difference_v=max(v['max_terminal_difference_v'] for v in measured['terminal_stress']),
        recorded_gates={k:v for k,v in r['result'].items() if k.endswith('_passed')},
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})


def run(cases):
    if not cases or len(set(cases))!=len(cases):raise ValueError('Require explicit unique completed counter cases')
    rows=[analyze(p) for p in cases];inputs={n:h for r in rows for n,h in r['inputs'].items()}
    paths=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Completed native clear evidence changed during analysis')
    identity=dict(version=VERSION,cases=[str(p.relative_to(ROOT)) for p in cases],inputs=inputs,numpy=np.__version__,byteorder=sys.byteorder)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'summary.json',dict(rows=rows,analysis_completed=True,parameters_changed=False,electrical_qualification_passed=False,qualified_phy=False,
        scope='Read-only original 26ns full-native clear/reassert diagnosis; no relaxed timing, waveform filtering or new circuit/PVT/PHY admission'))
    atomic(out/'state.json',dict(status='complete',analysis_completed=True,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',nargs='+',type=Path);a=p.parse_args()
    print(run([p.resolve() for p in a.cases]),flush=True)
