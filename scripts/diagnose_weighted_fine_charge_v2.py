#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind and remeasure the completed largest-fine-cell charging failure."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import probe_weighted_fine_control_v3 as pilot
from native_binary_raw_v2 import validate
from verify_conditioned_clock_v2 import compare_result

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='largest-native-fine-cap-charge-diagnosis-v2.1'
CONTEXT='weighted_fine_charge_diagnosis_v2'


def diagnose(parent):
    m=pilot.bound(parent);folder=parent/'1';r=json.loads((folder/'summary.json').read_text());spec=m['tasks'][1]['spec']
    if (r['task']!=m['tasks'][1] or r['error'] is not None or spec['variant']!='guarded' or spec['data_v']!=1.8
        or r['result']['control_settling_passed'] or not r['result']['terminal_screen_passed']
        or any(sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Require exact completed guarded high-bias settling failure')
    witness=m['identity']['devices']['guarded'];measured=pilot.measure(folder,spec,witness);compare_result(measured,r['result'])
    failures=[x for x in measured['settled_controls'] if not x['passed']]
    if [(x['code'],x['bit']) for x in failures]!=[(31,4),(16,4)] or any(x['driver_error_v']>.18 for x in failures):
        raise ValueError('Failure is not isolated to largest fine plate with settled controls')
    nodes=witness['cap_nodes']['4'];required={'v('+n.replace(':','.').lower()+')' for n in nodes}|{'v(en4)','v(enb4)','v(data)','v(vdd)'}
    names,w=validate(folder/'bench.raw',required,pilot.STOP);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e9
    cap=np.column_stack([w[:,idx['v('+n.replace(':','.').lower()+')']] for n in nodes]);minimum=np.min(cap,axis=1);maximum=np.max(cap,axis=1);rows=[]
    for start in [2.,6.]:
        window=np.flatnonzero((t>=start)&(t<start+1.99));low=window[minimum[window]<1.62]
        last=int(low[-1]) if len(low) else int(window[0])-1;settled=window[window>last]
        if not len(settled):raise ValueError('Plate never reaches original high-state limit before next control edge')
        samples=[]
        for elapsed in [.5,1.,1.5,1.9]:
            j=int(np.searchsorted(t,start+elapsed));samples.append(dict(elapsed_ns=float(t[j]-start),cap_min_v=float(minimum[j]),cap_max_v=float(maximum[j]),
                en_v=float(w[j,idx['v(en4)']]),enb_v=float(w[j,idx['v(enb4)']])))
        rows.append(dict(selection_ns=start,all_plate_nodes=len(nodes),observed_all_nodes_settled_after_ns=float(t[int(settled[0])]-start),samples=samples))
    paths=[parent/'manifest.json',folder/'summary.json',*[folder/n for n in r['files']],*[parent/n for n in m['libraries']]]
    paths += [Path(__file__),Path(pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/verify_conditioned_clock_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case='1',inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    pilot.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    pilot.atomic(out/'summary.json',dict(diagnosis_verified=True,original_settling_passed=False,terminal_screen_passed=True,failures=failures,charge_windows=rows,qualified_phy=False,
        scope='Completed SS40 fixed-1.8V high-data control case, exact original remeasurement and every resistor-connected bit-4 plate node; charging evidence only, no circuit repair or PHY admission'))
    bound(out);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['case']!='1'
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or not r['diagnosis_verified'] or r['original_settling_passed']
        or [(x['code'],x['bit']) for x in r['failures']]!=[(31,4),(16,4)]):raise ValueError('Fine charging failure witness changed')
    pilot.bound(ROOT/i['parent']);return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);a=p.parse_args();print(diagnose(a.parent.resolve()),flush=True)
