#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched full-duration DCDL runs with a larger transient iteration allowance.

Only ITL4 changes. Every native RC/MOS, tolerance, saved terminal, stimulus and
20 ns stop remains identical to the retained return-mux cases. Original live
solvers are untouched. Numerical/runtime evidence never admits a legal ROM.
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
import probe_dcdl_mux_return_v2 as parent_pilot
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import provenance

ROOT=parent_pilot.ROOT
VERSION='matched-native-dcdl-transient-iteration-pilot-v2.1'
CONTEXT='dcdl_iterations_v2'
ITERATIONS=100
PARENT_CASES=['0','2']


def fixture(text):
    if any(line.lower().startswith('.options itl4') for line in text.splitlines()):raise ValueError('Parent iteration limit already overridden')
    first,rest=text.split('\n',1)
    if first!='OpenLVDS '+parent_pilot.VERSION:raise ValueError('Require exact parent pilot title')
    return 'OpenLVDS '+VERSION+f'\n.options itl4={ITERATIONS}\n'+rest


def prepare(parent):
    pm=parent_pilot.bound(parent);i=pm['identity'];tasks=[]
    files=[parent/'manifest.json',*[parent/n for n in pm['libraries']],*[ROOT/n for n in i['inputs']]]
    for case in PARENT_CASES:
        task=pm['tasks'][int(case)];folder=parent/case;text=(folder/'bench.cir').read_text()
        if task['id']!=case or text!=parent_pilot.fixture(parent,task['spec'],i['devices']):raise ValueError('Parent deck regeneration changed')
        files.append(folder/'bench.cir');tasks.append(dict(id=case,spec=task['spec']))
    code=[Path(__file__),Path(parent_pilot.__file__),ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),itl4=ITERATIONS,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files+code},pdk_files=i['pdk_files'],simulator=provenance(),
        tasks=[dict(t) for t in tasks],scope='Matched full-duration native return-mux cases with ITL4=100; component RC, source mux/turn/control and ideal common wires; no ROM, full-PVT or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for task in tasks:
        folder=out/task['id'];folder.mkdir();write(folder/'bench.cir',fixture((parent/task['id']/'bench.cir').read_text()))
        task['deck_sha256']=sha(folder/'bench.cir')
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['itl4']!=ITERATIONS
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or provenance()!=i['simulator']):raise ValueError('Matched iteration context changed')
    pm=parent_pilot.bound(ROOT/i['parent'])
    if [t['id'] for t in m['tasks']]!=PARENT_CASES or [{k:v for k,v in t.items() if k!='deck_sha256'} for t in m['tasks']]!=i['tasks']:raise ValueError('Matched tasks changed')
    for task in m['tasks']:
        if task['spec']!=pm['tasks'][int(task['id'])]['spec'] or sha(out/task['id']/'bench.cir')!=task['deck_sha256']:raise ValueError('Matched deck/spec changed')
    return m,pm


def run(out):
    m,pm=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior matched iteration run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None;elapsed=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    elapsed=time.monotonic()-start
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode()
                result=parent_pilot.measure(folder,task['spec'],pm['identity']['devices'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,solver_wall_seconds=elapsed,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='matched_iteration_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
