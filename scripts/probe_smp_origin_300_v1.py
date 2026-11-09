#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate pinned-engine SMP with centered and unmodified complete references."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_input_current_origin_300_v1 as baseline
import run_native_smp_binary_300_v1 as runtime
from spice_dispatch import lease

ROOT=baseline.ROOT
PARENT=baseline.PARENT
VERSION='native-two-bank-smp-origin-validation-300-v1'
CONTEXT='smp_origin_pilot_300_v1'
sha=baseline.sha
atomic=baseline.atomic


def fixture(out,centered):
    text=(PARENT/'0/bench.cir').read_text()
    include=f'.include "{PARENT}/bank.spice"'
    card=baseline.admission.SOURCE.numerical_trial.CARD
    if text.count(include)!=1 or text.count(card)!=1 or 'I_BENCH_INPUT_CENTER' in text:
        raise ValueError('Require exact completed centered reference without input-current load')
    text=text.replace(include,f'.include "{out}/bank.spice"',1)
    if not centered:text=text.replace(card+'\n','',1)
    runtime.translate(text)
    return text


def prepare():
    source,evidence=baseline.admission.require_reference(baseline.PROOF)
    paths=[PARENT/'bank.spice',PARENT/'0/observations.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},spec=source['identity']['spec'],
        max_workers=1,priority=2,linear_solver='pinned_engine_default_smp',native_tolerances_unchanged=True,
        input_bench_current_a=0,combined_circuit_admitted=False,qualified_phy=False,
        scope='Two complete same-circuit SMP references only; no combined-circuit or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((PARENT/'bank.spice').read_bytes());tasks=[]
    for k,centered in enumerate((True,False)):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,centered))
        (folder/'observations.json').write_bytes((PARENT/'0/observations.json').read_bytes())
        tasks.append(dict(id=str(k),centered=centered,spec=identity['spec'],files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or (i['max_workers'],i['priority'])!=(1,2)
            or i['linear_solver']!='pinned_engine_default_smp' or i['native_tolerances_unchanged'] is not True
            or i['input_bench_current_a']!=0 or i['combined_circuit_admitted'] is not False
            or i['qualified_phy'] is not False or m['qualified_phy'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}):
        raise ValueError('SMP reference identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured SMP reference witness changed')
    if (sha(out/'bank.spice')!=m['bank_sha256'] or (out/'bank.spice').read_bytes()!=(PARENT/'bank.spice').read_bytes()
            or i['spec']!=json.loads((PARENT/'manifest.json').read_text())['identity']['spec']):
        raise ValueError('SMP native library or stimulus changed')
    expected=[]
    for k,centered in enumerate((True,False)):
        folder=out/str(k)
        if ((folder/'bench.cir').read_text()!=fixture(out,centered)
                or (folder/'observations.json').read_bytes()!=(PARENT/'0/observations.json').read_bytes()):
            raise ValueError('SMP exact native fixture changed')
        expected.append(dict(id=str(k),centered=centered,spec=i['spec'],files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('SMP complete numerical origins changed')
    return m


def pilot_passed(rows):
    if len(rows)!=2 or [(r['task']['id'],r['task']['centered']) for r in rows]!=[('0',True),('1',False)]:
        raise ValueError('Require both complete SMP numerical origins')
    return all(r['error'] is None and r['parity'] is not None and r['parity']['passed'] is True for r in rows)


def run(out):
    m=bound(out);spec=m['identity']['spec'];obs=json.loads((PARENT/'0/observations.json').read_text())
    old=json.loads((PARENT/'0/summary.json').read_text())['result']
    if baseline.metrology.measure(PARENT/'0',obs,spec,next_coarse=0,next_fine=0)!=old:
        raise ValueError('Original complete KLU reference does not reproduce')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial SMP experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=independent=parity=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_smp_binary_300_v1.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=baseline.metrology.measure(folder,obs,spec,next_coarse=0,next_fine=0)
                independent=baseline.independent.measure(folder,obs,spec,next_coarse=0,next_fine=0)
                if not baseline.same(result,independent):raise ValueError('Independent complete SMP metrics do not reproduce')
                parity=baseline.compare(PARENT/'0',folder,old,result)
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,independent_result=independent,parity=parity,
                     files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,smp_reference_pilot_passed=pilot_passed(rows),
            native_tolerances_unchanged=True,input_bench_current_a=0,combined_circuit_admitted=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=2,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured SMP experiment')
        print(run(a.artifact.resolve()),flush=True)
