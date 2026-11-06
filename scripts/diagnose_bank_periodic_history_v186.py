#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read completed periodic cases without touching the live producer or limits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_unguarded_bank_joint_periodic_v174 as source
from native_binary_raw_v2 import validate

ROOT=source.ROOT
sha=source.sha


def gate_mapping(parent,i):
    code='''import sys,json
from pathlib import Path
sys.path.insert(0,'scripts')
import measured_bank_observations_v145 as obs
import verify_unguarded_bank_joint_rc_v171 as rc
parent=Path(sys.argv[1]);i=json.loads((parent/'manifest.json').read_text())['identity'];p=rc.ROOT/i['parent'];ri=json.loads((p/'manifest.json').read_text())['identity'];r=json.loads((p/'summary.json').read_text())
mag=rc.ROOT/ri['parent']/'native'/(ri['top']+'.mag');ext=(rc.ROOT/r['original_extraction']['raw_netlist']).parent/(ri['top']+'_rcx.ext');bank=parent/'bank.spice'
_,labelled,body,_=obs.aliases(mag.read_text(),ext.read_text(),bank.read_text(),ri['graph'],ri['plan'])
lookup={d['name']:d for d in i['observations']['devices']};selected=[]
for w in body:
    if not w[0].startswith('X'):continue
    end=next((k for k,v in enumerate(w) if '=' in v),len(w));model=w[end-1]
    if 'fet_' not in model:continue
    if labelled.get(w[2])=='selected' and 'OUT' in {labelled.get(w[1]),labelled.get(w[3])}:selected.append(lookup['XD:'+w[0]])
if len(selected)!=32:raise ValueError('Require all 32 actual final-inverter input gates')
files=[p/'manifest.json',p/'summary.json',mag,ext,bank,Path(obs.__file__)]
print(json.dumps(dict(devices=selected,inputs={str(f.relative_to(rc.ROOT)):rc.sha(f) for f in files})))
'''
    p=subprocess.run([source.native.CAD,'-c',code,str(parent)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Actual periodic gate mapping refused:\n'+p.stderr[-2500:])
    return json.loads(p.stdout)


def diagnose(parent,cases):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if i['version']!=source.VERSION or parent.parent!=ROOT/'build/diagnostics'/source.CONTEXT:raise ValueError('Require actual unguarded periodic producer')
    mapping=gate_mapping(parent,i);nodes=sorted({d['terminals'][1] for d in mapping['devices']})
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    files={str((parent/'manifest.json').relative_to(ROOT)):sha(parent/'manifest.json'),**mapping['inputs']};rows=[]
    for case in cases:
        folder=parent/str(case);r=json.loads((folder/'summary.json').read_text());task=m['tasks'][case];s=task['spec']
        if r['task']!=task or r['spec']!=s or r['error'] is not None or any(sha(folder/n)!=h for n,h in r['files'].items()):raise ValueError('Require complete unchanged native periodic case')
        measured=source.measure(folder,dict(i,spec=s))
        if measured!=r['result']:raise ValueError('Stored periodic metrics do not reproduce')
        names,w=validate(folder/'bench.raw',{column(n) for n in nodes},s['stop_ns']*1e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
        period=1e6/s['frequency_mhz'];gate_states=[]
        for k in range(s['cycles']):
            reference=2100+k*period
            values=[float(np.interp(reference,t,w[:,idx[column(n)]])) for n in nodes]
            interval=(t>=reference)&(t<reference+period)
            gate_states.append(dict(cycle=k,reference_rise_ps=reference,at_reference_min_v=min(values),at_reference_max_v=max(values),
                cycle_min_v=min(float(np.min(w[interval,idx[column(n)]])) for n in nodes),
                cycle_max_v=max(float(np.max(w[interval,idx[column(n)]])) for n in nodes)))
        delays=measured['edge_delays_ps'];last_spans={edge:max(v[-4:])-min(v[-4:]) for edge,v in delays.items() if len(v)==8}
        rows.append(dict(case=case,spec=s,edge_delays_ps=delays,whole_trace_spans_ps=measured['repeated_delay_span_ps'],last_four_delay_spans_ps=last_spans,
            maximum_period_error_ps=measured['maximum_period_error_ps'],output_duty_percent=measured['output_duty_percent'],
            period_screen_passed=measured['period_screen_passed'],repeated_delay_screen_passed=measured['repeated_delay_screen_passed'],
            full_swing_pulses_passed=measured['full_swing_pulses_passed'],terminal_screen_passed=measured['terminal_screen_passed'],
            output_slew_domain_passed=measured['current_downstream_250ps_slew_domain_passed'],gate_states=gate_states))
        files.update({str((folder/n).relative_to(ROOT)):sha(folder/n) for n in ['summary.json',*r['files']]})
    if any(sha(ROOT/n)!=h for n,h in files.items()):raise ValueError('Completed periodic data changed during diagnosis')
    return dict(parent=str(parent.relative_to(ROOT)),cases=rows,final_inverter_gate_devices=mapping['devices'],inputs=files,code_sha256=sha(Path(__file__)),
        scope='Read-only exact native gate/edge history; original startup/repetition/period/slew gates unchanged, no circuit or PHY admission',qualified_phy=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--cases',type=int,nargs='+',default=[0,1,2,3]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=diagnose(a.artifact.resolve(),a.cases);out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
    print(out)
