#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Actual routed clock transport at 390/400/410 MHz and 40/50/60% duty.

Admits only the complete passing whole-bank sparse screen; all native
observations, original electrical limits and downstream slew gates remain.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_measured_balanced_joint_sparse_v153 as sparse
import regenerated_bank_periodic_measure_v67 as periodic
import numpy as np

native=sparse.native

ROOT=native.ROOT
zero=native.zero
sha=native.sha
VERSION='actual-measured-balanced-joint-rc-390-400-410mhz-duty40-50-60-full-native-v154.1'
CONTEXT='measured_balanced_joint_periodic_v154'
SCOPE='27 actual routed SS/40 clock-transport cases: three sparse codes, 390/400/410 MHz, 40/50/60% duty, complete native observations and original 250 ps slew; no DCC output, dense/update/all-PVT/electrical/PHY admission'


def specifications(spec):
    return [dict(spec,coarse=c,fine=f,frequency_mhz=mhz,duty=d,cycles=8,stop_ns=25)
            for c,f in ((0,0),(0,31),(1,0)) for mhz in (390,400,410) for d in (.4,.5,.6)]


def fixture(out,i,s):
    text=native.fixture(out,dict(i,spec=s));title='OpenLVDS '+native.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original native fixture changed')
    width=s['input_slew_ps']/1e12/(2*np.arctanh(.8));period=1e-6/s['frequency_mhz']
    wave='+'.join(f'0.9*(tanh((time-{2.1e-9+k*period:.17g})/{width:.17g})-tanh((time-{2.1e-9+(k+s["duty"])*period:.17g})/{width:.17g}))' for k in range(s['cycles']))
    rows=text.splitlines()
    if sum(r.startswith('BIN IN 0 V=') for r in rows)!=1 or rows.count('.tran 2p 20n 0 2p')!=1:
        raise ValueError('Original complete pulse fixture changed')
    rows=['BIN IN 0 V={'+wave+'}' if r.startswith('BIN IN 0 V=') else f'.tran 2p {s["stop_ns"]}n 0 2p' if r=='.tran 2p 20n 0 2p' else r for r in rows]
    return ('\n'.join(rows)+'\n').replace(title,'OpenLVDS '+VERSION+'\n',1)


def prepare(parent):
    source=sparse.bound(parent);fi=source['identity'];r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=2,consumed_zero_cases=1,errors=0,qualified_phy=False)
        or len(r['rows'])!=2 or r['comparison']!=sparse.compare(r['rows'],fi['source_zero_result'])
        or not r['comparison']['joint_rc_sparse_feasibility_passed']):
        raise ValueError('Require complete passing actual joint-RC sparse screen')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json','bank.spice']]
    paths += [ROOT/n for n in fi['inputs']]
    for task,row in zip(source['tasks'],r['rows']):
        case=parent/task['id']
        if (row!=json.loads((case/'summary.json').read_text()) or row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None
            or any(sha(case/n)!=h for n,h in row['files'].items()) or sparse.measure(case,dict(fi,spec=task['spec']))!=row['result']):
            raise ValueError('Actual sparse native result does not reproduce')
        paths += [case/'summary.json',*[case/n for n in row['files']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(fi,version=VERSION,source_sparse=str(parent.relative_to(ROOT)),source_sparse_result=r['comparison'],specs=specifications(fi['spec']),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for k,s in enumerate(i['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,i,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    (out/'manifest.json').write_text(json.dumps(dict(identity=i,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or zero.engine()!='ngspice' or zero.provenance()!=i['simulator'] or i['max_workers']!=2
        or i['spec']!=native.spec(i['profile']) or sha(Path(native.CAD))!=i['cad']['sha256']
        or i['specs']!=specifications(i['spec']) or len(m['tasks'])!=27
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['source_sparse']/'bank.spice')!=m['bank_sha256']):
        raise ValueError('Actual joint-RC periodic context changed')
    receipt=json.loads((ROOT/i['source_sparse']/'summary.json').read_text())
    if receipt['comparison']!=i['source_sparse_result'] or not receipt['comparison']['joint_rc_sparse_feasibility_passed']:
        raise ValueError('Consumed actual sparse result changed')
    for k,t in enumerate(m['tasks']):
        deck=out/str(k)/'bench.cir'
        if t['id']!=str(k) or t['spec']!=i['specs'][k] or sha(deck)!=t['deck_sha256'] or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Actual joint-RC periodic fixture changed')
    return m


def measure(folder,i):
    return dict(periodic.measure(folder,i),scope=SCOPE)


def compare(rows,specs):
    if not specs or len(rows)!=len(specs) or any(row['error'] is not None for row in rows):return None
    if specs!=specifications(native.spec(specs[0]['profile'])) or [r['spec'] for r in rows]!=specs:raise ValueError('Periodic matrix coverage changed')
    whole=all(r['result']['whole_bank_rc_retained'] for r in rows)
    return dict(all_periodic_transport_cases_passed=whole and all(r['result']['periodic_transport_screen_passed'] for r in rows),
                all_current_clock_interface_cases_passed=whole and all(r['result']['current_clock_interface_screen_passed'] for r in rows),
                actual_joint_rc_retained=whole,
                all_pvt_covered=False,corrected_dcc_output_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial actual joint-RC periodic campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,dict(i,spec=task['spec']))
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows,i['specs']),source_sparse=i['source_sparse'],scope=SCOPE,qualified_phy=False))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(row['error'] is not None for row in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
