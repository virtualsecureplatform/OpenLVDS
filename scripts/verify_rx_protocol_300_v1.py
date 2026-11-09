#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh RX protocol regression at the 300 MHz profile; no electrical admission."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import clocking_profile_300 as policy

ROOT=policy.ROOT
VERSION='rx-real-control-protocol-independent-phase-300-v1'
CONTEXT='rx_protocol_functional_300_v1'
MODES=('scan_payload_and_delivered_phase_loss','missing_physical_settling','wrong_settling_tag',
    'unadmitted_rom','unadmitted_deskew','unadmitted_dcc','missing_dll_lock','single_overall_deadline',
    'source_loss_during_hold','retrain_cancels_pending_update','dll_lock_loss','dll_failure','table_revoked',
    'final_revalidation_failure','no_eye')
SCOPE='Real RX transaction, scan, framing, warmup and fault RTL with synthetic eye/settling, ideal phases and supplied DLL lock; no analog/native delay, real DLL calibration or PHY admission'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def atomic(path,value):
    temporary=path.with_name(path.name+'.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def specifications():
    req=policy.load()['requirements']
    cases=[dict(id=str(k),kind='scan',mhz=f,duty=d,mode=m,name=MODES[m])
           for k,(f,d,m) in enumerate(itertools.product(req['clock_test_mhz'],req['clock_duty'],range(len(MODES))))]
    cases += [dict(id=str(len(cases)+k),kind='loss',mhz=f,duty=.5,mode=None,name='all_160_warmup_stop_phases')
              for k,f in enumerate(req['clock_test_mhz'])]
    return cases


def sources():
    return sorted((ROOT/'rtl/v2').glob('*.v'))+[ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v',
        ROOT/'tb/tb_dcc_release_v2.v',ROOT/'tb/tb_rx_training_300_v1.v',ROOT/'tb/tb_rx_clock_loss_v3.v']


def prepare():
    files=sources()+[Path(__file__).resolve(),ROOT/'scripts/clocking_profile_300.py',ROOT/'clocking_300mhz.json']
    runtime={}
    for name in ('iverilog','vvp'):
        path=shutil.which(name)
        if path is None:raise ValueError('Use scripts/env.sh --tools --ngspice')
        runtime[name]=dict(path=path,sha256=sha(Path(path)))
    identity=dict(version=VERSION,inputs={str(p):sha(p) for p in files},runtime=runtime,
        specs=specifications(),max_workers=2,scope=SCOPE,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or i['scope']!=SCOPE or i['max_workers']!=2
            or i['qualified_phy'] is not False or m['qualified_phy'] is not False
            or any(sha(Path(n))!=h for n,h in i['inputs'].items())
            or any(shutil.which(n)!=r['path'] or sha(Path(r['path']))!=r['sha256'] for n,r in i['runtime'].items())):
        raise ValueError('RX protocol regression inputs changed')
    return i


def one(out,task):
    folder=out/task['id'];folder.mkdir();top='tb_rx_training_300_v1' if task['kind']=='scan' else 'tb_rx_clock_loss_v3'
    options=([f'-P{top}.MHZ={task["mhz"]}',f'-P{top}.DUTY_PERCENT={round(task["duty"]*100)}',f'-P{top}.MODE={task["mode"]}']
             if task['kind']=='scan' else [f'-P{top}.HALF_PERIOD={500/task["mhz"]:.12f}'])
    command=['iverilog','-g2012','-Wall','-s',top,*options,'-o',str(folder/'test.vvp'),*map(str,sources())]
    build=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (folder/'compile.log').write_text(build.stdout+build.stderr)
    if build.returncode:return dict(task=task,passed=False,error='Compilation failed')
    run=subprocess.run(['vvp',str(folder/'test.vvp')],capture_output=True,text=True,timeout=90)
    log=run.stdout+run.stderr;(folder/'run.log').write_text(log)
    if task['kind']=='scan':
        passed=bool(run.returncode==0 and re.search(r'^PASS 300 RX safe scan, .*mode=\s*'+str(task['mode'])+r'\s*$',log,re.M))
        return dict(task=task,passed=passed,returncode=run.returncode)
    match=re.search(r'^PASS v3 RX warmup clock loss: 160 phases half_period=\S+ worst=\s*(\d+) cycles$',log,re.M)
    return dict(task=task,passed=bool(run.returncode==0 and match and int(match[1])<=8),
        warmup_stop_phases=160 if match else 0,worst_loss_management_cycles=int(match[1]) if match else None,returncode=run.returncode)


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior protocol regression')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda task:one(out,task),i['specs']))
            bound(out);passed=bool(len(rows)==138 and all(r['passed'] for r in rows))
            atomic(out/'summary.json',dict(rows=rows,passed=passed,scan_cases=135,
                warmup_stop_phases=sum(r.get('warmup_stop_phases',0) for r in rows),
                delay_model_admitted=False,analog_clock_admitted=False,qualified_phy=False,scope=SCOPE))
            atomic(out/'state.json',dict(status='complete' if passed else 'failed',cases=len(rows),qualified_phy=False))
            if not passed:raise ValueError('300-profile RX protocol regression failed; retain every native RTL failure')
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    out=prepare();print(out,flush=True);print(run(out),flush=True)
