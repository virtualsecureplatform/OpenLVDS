#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test input-source current centering against one complete native reference."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import input_current_origin_300_v1 as trial
import probe_tg2_entry_domain_300_v1 as admission
import two_bank_native_measure_300_v1 as metrology
import two_bank_independent_measure_300_v1 as independent
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from replay_bank_300_v2 import same
from spice_dispatch import lease

ROOT=admission.ROOT
PARENT=admission.PARENT
PROOF=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v1/5a13c2fa7eabefdd'
VERSION='native-two-bank-input-current-origin-validation-300-v1'
CONTEXT='input_current_origin_pilot_300_v1'
sha=admission.sha
atomic=admission.atomic


def booleans(value,path=()):
    if isinstance(value,bool):return {path:value}
    if isinstance(value,dict):return {p:v for k,x in value.items() for p,v in booleans(x,path+(k,)).items()}
    if isinstance(value,list):return {p:v for k,x in enumerate(value) for p,v in booleans(x,path+(k,)).items()}
    return {}


def compare(reference,candidate,old,new):
    names,a=validate(reference/'bench.raw',set(),40e-9);other,b=validate(candidate/'bench.raw',set(names),40e-9)
    method=admission.SOURCE.prior.numerical
    forward=method.wave_difference(names,a,other,b);reverse=method.wave_difference(other,b,names,a)
    dc=max(abs(float(a[0,names.index(n)])-float(b[0,other.index(n)])) for n in names if n.startswith('v('))
    errors=[]
    for node in ('v(in)','v(out)','v(next_out)'):
        for up in (True,False):
            x=crossings(a[:,0]*1e12,a[:,names.index(node)],.9,up)
            y=crossings(b[:,0]*1e12,b[:,other.index(node)],.9,up)
            if len(x)!=8 or len(y)!=8:return dict(passed=False,reason='Missing complete startup-inclusive source/output events')
            errors.extend(abs(v-w) for v,w in zip(x,y))
    flags=booleans(old)==booleans(new)
    maximum=max(forward['maximum_all_vector_error_v'],reverse['maximum_all_vector_error_v'])
    return dict(passed=bool(a[0,0]==b[0,0]==0 and dc<=1e-9 and maximum<=.002 and max(errors)<=.25 and flags),
        forward=forward,reverse=reverse,maximum_dc_voltage_error_v=dc,maximum_crossing_error_ps=max(errors),
        all_gate_classifications_preserved=flags)


def fixture(out):
    text=(PARENT/'0/bench.cir').read_text();library=(PARENT/'bank.spice').read_text()
    old=f'.include "{PARENT}/bank.spice"'
    if text.count(old)!=1:raise ValueError('Original loaded reference library include changed')
    return trial.fixture(text.replace(old,f'.include "{out}/bank.spice"',1),library)


def prepare():
    source,inputs=admission.require_reference(PROOF)
    paths=[PARENT/'bank.spice',PARENT/'0/observations.json']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**inputs,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),reference_proof=str(PROOF.relative_to(ROOT)),
        inputs=inputs,guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},spec=source['identity']['spec'],
        current_card=trial.CARD,max_workers=1,priority=2,external_input_bench_power_excluded=True,
        input_bench_dc_a=0,input_bench_peak_a=.001,combined_circuit_admitted=False,qualified_phy=False,
        scope='One native input-current-origin validation only; no transfer to combined DCC, physical timing repair or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);folder=out/'0';folder.mkdir()
    (out/'bank.spice').write_bytes((PARENT/'bank.spice').read_bytes());(folder/'bench.cir').write_text(fixture(out))
    (folder/'observations.json').write_bytes((PARENT/'0/observations.json').read_bytes())
    task=dict(id='0',spec=identity['spec'],files={n:sha(folder/n) for n in ('bench.cir','observations.json')})
    atomic(out/'manifest.json',dict(identity=identity,tasks=[task],bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['reference_proof']!=str(PROOF.relative_to(ROOT))
            or i['current_card']!=trial.CARD or (i['max_workers'],i['priority'])!=(1,2)
            or i['external_input_bench_power_excluded'] is not True or i['input_bench_dc_a']!=0 or i['input_bench_peak_a']!=.001
            or i['combined_circuit_admitted'] is not False or i['qualified_phy'] is not False or m['qualified_phy'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}):
        raise ValueError('Input-origin diagnostic identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):raise ValueError('Captured input-origin reference changed')
    if any(str((PROOF/n).relative_to(ROOT)) not in i['guards'] for n in ('manifest.json','summary.json','state.json')):
        raise ValueError('Independent source receipt binding changed')
    if (sha(out/'bank.spice')!=m['bank_sha256'] or (out/'bank.spice').read_bytes()!=(PARENT/'bank.spice').read_bytes()
            or (out/'0/bench.cir').read_text()!=fixture(out)
            or (out/'0/observations.json').read_bytes()!=(PARENT/'0/observations.json').read_bytes()):
        raise ValueError('Input-origin native circuit or observations changed')
    parent=json.loads((PARENT/'manifest.json').read_text())
    if i['spec']!=parent['identity']['spec']:raise ValueError('Original complete loaded stimulus changed')
    task=dict(id='0',spec=i['spec'],files={n:sha(out/'0'/n) for n in ('bench.cir','observations.json')})
    if m['tasks']!=[task]:raise ValueError('Input-origin task changed')
    return m


def run(out):
    m=bound(out);i=m['identity'];folder=out/'0';obs=json.loads((folder/'observations.json').read_text())
    old=json.loads((PARENT/'0/summary.json').read_text())['result']
    if metrology.measure(PARENT/'0',obs,i['spec'],next_coarse=0,next_fine=0)!=old:
        raise ValueError('Original complete loaded reference does not reproduce')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial input-origin experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));error=result=witness=parity=None
        try:
            with lease(ROOT,priority=2,label=CONTEXT+'_0'):
                bound(out,full=False)
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
            result=metrology.measure(folder,obs,i['spec'],next_coarse=0,next_fine=0)
            witness=independent.measure(folder,obs,i['spec'],next_coarse=0,next_fine=0)
            if not same(result,witness):raise ValueError('Independent complete input-origin metrics do not reproduce')
            parity=compare(PARENT/'0',folder,old,result)
        except Exception as exc:error=str(exc)
        atomic(folder/'summary.json',dict(task=m['tasks'][0],error=error,result=result,independent_result=witness,parity=parity,
            files={p.name:sha(p) for p in folder.iterdir() if p.is_file()}))
        bound(out)
        atomic(out/'summary.json',dict(error=error,result=result,parity=parity,
            numerical_origin_passed_for_reference_case=bool(error is None and parity['passed']),
            combined_circuit_admitted=False,qualified_phy=False,
            scope='Single complete two-bank numerical reference only; every new circuit still needs its own parity and physical gates'))
        atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured diagnostic directory')
        print(run(a.artifact.resolve()),flush=True)
