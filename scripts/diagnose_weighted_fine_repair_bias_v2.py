#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure completed guarded biases without admitting the pending four-case gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import probe_weighted_fine_control_v3 as before
import probe_weighted_fine_control_v4 as after
import verify_weighted_fine_control_v3 as before_verification
import verify_weighted_fine_control_v4 as after_verification
from native_binary_raw_v2 import validate

ROOT=after.ROOT
VERSION='matched-guarded-fine-repair-completed-bias-diagnosis-v2.1'
CONTEXT='weighted_fine_repair_bias_diagnosis_v2'


def checked_cases(pilot,verifier,parent):
    m=pilot.bound(parent);witnesses=verifier.regenerate(parent,m);rows=[]
    files=[parent/'manifest.json',*[parent/n for n in m['libraries']]]
    for number,bias in enumerate([0.,1.8]):
        folder=parent/str(number);task=m['tasks'][number];spec=task['spec'];r=json.loads((folder/'summary.json').read_text())
        if (r['task']!=task or r['error'] is not None or spec['variant']!='guarded' or spec['data_v']!=bias
            or (folder/'bench.cir').read_text()!=pilot.fixture(parent,spec,witnesses['guarded'])
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
            or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):
            raise ValueError('Require the exact two complete guarded DATA bias cases')
        measured=pilot.measure(folder,spec,witnesses['guarded'])
        if measured!=r['result']:raise ValueError('Guarded native bias waveform remeasurement changed')
        rows.append(dict(task=task,result=measured));files += [folder/n for n in ['summary.json',*r['files']]]
    return m,witnesses['guarded'],rows,files


def charge_windows(parent,witness):
    nodes=witness['cap_nodes']['4'];folder=parent/'1'
    requested={'v('+n.replace(':','.').lower()+')' for n in nodes}
    names,w=validate(folder/'bench.raw',requested,after.STOP);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e9
    cap=np.column_stack([w[:,idx['v('+n.replace(':','.').lower()+')']] for n in nodes]);error=np.max(np.abs(cap-1.8),axis=1)
    rows=[]
    for start,code in [(2.,31),(6.,16)]:
        window=np.flatnonzero((t>=start)&(t<start+1.99));bad=window[error[window]>.18]
        last=int(bad[-1]) if len(bad) else int(window[0])-1;settled=window[window>last]
        if not len(settled):raise ValueError('Largest plate never settles before the next control transition')
        rows.append(dict(code=code,selection_ns=start,all_plate_nodes=len(nodes),
            all_nodes_stay_within_original_limit_after_ns=float(t[int(settled[0])]-start),
            original_deadline_ns=1.5,cap_error_limit_v=.18))
    return rows


def diagnose(original,repaired):
    bm,bw,br,files=checked_cases(before,before_verification,original)
    am,aw,ar,paths=checked_cases(after,after_verification,repaired);files+=paths
    bi=bm['identity'];ai=am['identity'];name=after.circuit.unit.name(4)
    if (bi['clock']!=ai['clock'] or bi['fine_cells']!=ai['fine_cells'] or bi['orders']!=ai['orders']
        or [r['task']['spec'] for r in br]!=[r['task']['spec'] for r in ar]):raise ValueError('Bias comparison changed more than the selected fine repair')
    pattern=r'(?ims)^\.subckt[ \t]+'+re.escape(name)+r'[ \t]+.*?^\.ends(?:[ \t]+[^\n]*)?$'
    old=(original/'cells.spice').read_text();new=(repaired/'cells.spice').read_text()
    if (len(re.findall(pattern,old))!=1 or len(re.findall(pattern,new))!=1 or re.findall(pattern,old)==re.findall(pattern,new)
        or re.sub(pattern,'',old)!=re.sub(pattern,'',new)
        or any((original/n).read_text()!=(repaired/n).read_text() for n in bm['libraries'] if n!='cells.spice')):
        raise ValueError('More than the largest fine-cell RC block changed')
    failures=[r for r in br[1]['result']['settled_controls'] if not r['passed']]
    if ([(r['code'],r['bit']) for r in failures]!=[(31,4),(16,4)]
        or not all(r['result']['terminal_screen_passed'] for r in br)
        or not all(r['result']['component_pilot_passed'] for r in ar)):
        raise ValueError('Require original isolated charging failure and two successful repaired guarded biases')
    windows_before=charge_windows(original,bw);windows_after=charge_windows(repaired,aw)
    if not all(r['all_nodes_stay_within_original_limit_after_ns']<=1.5 for r in windows_after):
        raise ValueError('Repaired charging does not meet the original deadline')
    biases=[]
    for a,b in zip(br,ar):
        biases.append(dict(data_v=b['task']['spec']['data_v'],
            before_settling_passed=a['result']['control_settling_passed'],after_settling_passed=b['result']['control_settling_passed'],
            before_terminal_peak_v=a['result']['maximum_terminal_difference_v'],after_terminal_peak_v=b['result']['maximum_terminal_difference_v'],
            after_maximum_cap_error_v=max(s['cap_error_v'] for s in b['result']['settled_controls']),
            largest_on_cap_errors_before=[s for s in a['result']['settled_controls'] if s['bit']==4 and s['code'] in [31,16]],
            largest_on_cap_errors_after=[s for s in b['result']['settled_controls'] if s['bit']==4 and s['code'] in [31,16]]))
    files += [Path(__file__),Path(before.__file__),Path(after.__file__),Path(before_verification.__file__),Path(after_verification.__file__),ROOT/'scripts/native_binary_raw_v2.py']
    identity=dict(version=VERSION,original=str(original.relative_to(ROOT)),repaired=str(repaired.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):after.sha(p) for p in files})
    if any(after.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Bias comparison evidence changed')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);after.atomic(out/'summary.json',dict(identity=identity,
        guarded_bias_repair_diagnosed=True,only_largest_fine_rc_changed=True,biases=biases,
        high_bias_charge_windows_before=windows_before,high_bias_charge_windows_after=windows_after,
        required_four_case_gate_satisfied=False,bank_execution_admitted=False,qualified_phy=False,
        scope='Four fully remeasured guarded cases across old/repaired native models; two DATA biases only, not the repaired campaign source-driver comparisons, complete gate, active-clock, whole-bank or all-PVT/PHY admission'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('repaired',type=Path)
    a=p.parse_args();print(diagnose(a.original.resolve(),a.repaired.resolve()),flush=True)
