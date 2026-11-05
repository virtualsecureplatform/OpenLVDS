#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Five fresh joint-RC codes after independently verified regenerated zero."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import itertools
import numpy as np
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
import probe_regenerated_bank_joint_zero_v61 as zero
import verify_regenerated_bank_joint_zero_v62 as proof
import regenerated_bank_sparse_metrics_v63 as metrics

ROOT=zero.ROOT
baseline=zero.baseline
sha=zero.sha
VERSION='regenerated-actual-joint-rc-five-codes-plus-verified-zero-v63.1'
CONTEXT='regenerated_bank_sparse_v63'
SCOPE='Six SS40 sparse codes on the same actual regenerated joint-RC bank; no dense/update/periodic/all-PVT, legal table, electrical or PHY admission'


def specifications():return [dict(zero.spec(),coarse=c,fine=f) for c,f in metrics.CODES[1:]]


def inherited(evidence):
    binding=proof.bound(evidence);receipt=json.loads((evidence/'summary.json').read_text())
    if not receipt['joint_rc_zero_screen_passed']:raise ValueError('Require independently passed routed zero')
    parent=ROOT/binding['parent'];m=zero.bound(parent);r=json.loads((parent/'0/summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
            or r['error'] is not None or r['result']!=receipt['result']
            or r['spec']!=zero.spec() or any(sha(parent/'0'/n)!=h for n,h in r['files'].items())
            or zero.measure(parent,m['identity'])!=receipt['result']):
        raise ValueError('Complete inherited routed zero changed')
    return parent,m,receipt


def fixture(out,i,s):
    text=zero.fixture(out,dict(i,spec=s));title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed zero fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(evidence):
    parent,m,receipt=inherited(evidence);old=m['identity'];binding=json.loads((evidence/'manifest.json').read_text())['identity']
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in binding['inputs']],parent/'bank.spice']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),zero_parent=str(parent.relative_to(ROOT)),
        specs=specifications(),top=old['top'],ports=old['ports'],model=old['model'],observations=old['observations'],
        netlist=old['netlist'],pdk_files=old['pdk_files'],simulator=old['simulator'],cad=old['cad'],
        zero_result=receipt['result'],inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);zero.baseline.write(out/'bank.spice',(parent/'bank.spice').read_text());tasks=[]
    for n,s in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();zero.baseline.write(folder/'bench.cir',fixture(out,identity,s))
        tasks.append(dict(id=str(n),spec=s,deck_sha256=sha(folder/'bench.cir')))
    zero.baseline.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={'bank.spice':sha(out/'bank.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];o=i['observations']
    original=json.loads((ROOT/i['zero_parent']/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or i['max_workers']!=2 or zero.engine()!='ngspice' or zero.provenance()!=i['simulator']
            or len(o['devices'])!=951 or len(o['programming_gates'])!=133 or o['observed_canonical_nets']!=150
            or any(i[k]!=original[k] for k in ('top','ports','model','observations','netlist','pdk_files','simulator','cad'))
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
            or sha(Path(i['cad']['path']))!=i['cad']['sha256'] or sha(out/'bank.spice')!=m['libraries']['bank.spice']
            or (out/'bank.spice').read_bytes()!=(ROOT/i['netlist']).read_bytes()
            or len(m['tasks'])!=len(i['specs'])):raise ValueError('Regenerated sparse context changed')
    evidence=json.loads((ROOT/i['evidence']/'summary.json').read_text())
    if not evidence['joint_rc_zero_screen_passed'] or i['zero_result']!=evidence['result']:raise ValueError('Inherited routed zero changed')
    for n,t in enumerate(m['tasks']):
        deck=out/str(n)/'bench.cir'
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or t['deck_sha256']!=sha(deck) or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Sparse code or native fixture changed')
    return m


def measure(folder,i,s):
    # Own the general-code checker below. Its voltages, complete-waveform,
    # pulse counting and repeatability limits match the immutable zero gate.
    return measure_trace(folder,dict(i,spec=s))


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial sparse campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                zero.baseline.write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=i['max_workers']) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        comparison=None
        if all(r['error'] is None for r in rows):comparison=metrics.compare([dict(spec=zero.spec(),result=i['zero_result'],error=None),*rows])
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=comparison,qualified_phy=False,scope=SCOPE))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


def measure_trace(folder,i):
    o=i['observations'];s=i['spec'];targets=control_targets(s['coarse'],s['fine'])
    def column(n):return 'v('+n.replace(':','.').lower()+')'
    requested={column(n) for d in o['devices'] for n in d['terminals'] if n!='0'}
    requested.update(column(c['node']) for c in o['controls']);requested.update(column(n) for n in ('IN','OUT','VDD',*baseline.circuit.encode(s['coarse'],s['fine'])))
    names,w=validate(folder/'bench.raw',requested,20e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
    if t[0]>1e-6:raise ValueError('Native trace omits startup interval')
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,idx[column(n)]]
    samples=[]
    for base in (0,10000):
        window=(t>=base)&(t<=base+10000);sample={}
        for up,label in ((True,'rise'),(False,'fall')):
            a=baseline.crossings(t[window],get('IN')[window],up);b=baseline.crossings(t[window],get('OUT')[window],up)
            if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra pulse or wrong native epoch')
            sample[label+'_delay_ps']=float(b[0]-a[0])
        samples.append(sample)
    stress=[]
    for d in o['devices']:
        peak=max(float(np.max(np.abs(get(a)-get(b)))) for a,b in itertools.combinations(d['terminals'],2))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
    stable=t>=1500;controls=[];gates=[]
    for c in o['controls']:
        deviation=float(np.max(np.abs(get(c['node'])[stable]-1.8*targets[c['control']])))
        controls.append(dict(c,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for g in o['programming_gates']:
        deviation=float(np.max(np.abs(get(g['gate_node'])[stable]-1.8*targets[g['control']])))
        gates.append(dict(g,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for pin,value in baseline.circuit.encode(s['coarse'],s['fine']).items():
        if np.max(np.abs(get(pin)-1.8*value))>.01:raise ValueError('External control stimulus changed')
    repeat={k:abs(samples[1][k+'_delay_ps']-samples[0][k+'_delay_ps']) for k in ('rise','fall')}
    passed=all(s['passed'] for s in stress) and all(c['passed'] for c in controls+gates) and all(v<=20 for v in repeat.values())
    return dict(samples=samples,terminal_stress=stress,controls=controls,programming_gates=gates,
                terminal_screen_passed=all(s['passed'] for s in stress),control_settling_passed=all(c['passed'] for c in controls+gates),
                repeated_delay_difference_ps=repeat,static_native_screen_passed=bool(passed),
                whole_bank_rc_retained=True,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
