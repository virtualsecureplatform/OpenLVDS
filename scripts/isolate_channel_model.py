#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate delayed-channel numerics; validate equivalent zero-loss LTRA first."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from dll_measurements import read_wave
from spice_engine import command,provenance
from spice_dispatch import lease
from reduce_rc import number

ROOT=Path(__file__).resolve().parents[1]
CASES=['zero_delay','ltra_lossless']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def ltra(name,a,b,z,delay):
    # With LEN=1, sqrt(L/C)=Z0 and sqrt(L*C)=TD exactly.
    return f'O{name} {a} 0 {b} 0 M{name}\n.model M{name} LTRA R=0 G=0 L={z*delay:.17g} C={delay/z:.17g} LEN=1'


def fixture(deck,old,new,mode):
    if mode not in CASES:raise ValueError('Select bounded channel isolation case')
    include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 12n 0 1p']:raise ValueError('Require unchanged original 12 ns/1 ps coupled fixture')
    expected=dict(TD0=('D0B','D0F',1.3e-9),TD1=('D1B','D1F',1.3e-9),TC0=('C0B','C0F',1.2e-9),TC1=('C1B','C1F',1.2e-9))
    rows=deck.splitlines();found=[];ports=[]
    for index,line in enumerate(rows[1:],1):
        if not line.startswith('T'):continue
        w=line.split()
        if len(w)!=7 or w[0] not in expected or w[2]!='0' or w[4]!='0' or not w[5].startswith('Z0=') or not w[6].startswith('TD='):raise ValueError('Unexpected channel line')
        a,b,delay=expected[w[0]];z=number(w[5].split('=')[1]);actual=number(w[6].split('=')[1])
        if w[1]!=a or w[3]!=b or z!=50 or not np.isclose(actual,delay,rtol=1e-12,atol=0):raise ValueError('Channel ports/impedance/delay changed')
        rows[index]=f'VZERO_{w[0]} {a} {b} 0' if mode=='zero_delay' else ltra(w[0],a,b,z,delay)
        found.append(w[0]);ports.append(dict(name=w[0],z0_ohm=z,delay_s=delay,L_h=z*delay,C_f=delay/z))
    if len(found)!=4 or set(found)!=set(expected):raise ValueError('Require all four original channel legs')
    result='\n'.join(rows)+'\n'
    return result.replace(include,f'.include "{new}/library.spice"'),ports


def calibration(load):
    points=[(0.,.2)];previous=.2
    for i in range(16):
        center=.5+i*.625;value=.6 if i%2==0 else .2
        half=(260/.6/2000) if load==50 else .05
        points.extend([(center-half,previous),(center+half,value)]);previous=value
    source='PWL('+' '.join(f'{t:.12g}n {v:.12g}' for t,v in points)+')'
    source_ohm=50 if load==50 else 10
    rows=['Passive line implementation calibration','.options timeint method=gear reltol=1e-4 abstol=1e-12',
          f'VS SRC 0 {source}',f'RT SRC IN_T {source_ohm}',f'RO SRC IN_O {source_ohm}',
          'TREF IN_T 0 OUT_T 0 Z0=50 TD=1.2n',ltra('REF','IN_O','OUT_O',50,1.2e-9),
          f'RLT OUT_T 0 {load}',f'RLO OUT_O 0 {load}',
          '.tran 1p 12n 0 1p','.print tran V(SRC) V(OUT_T) V(OUT_O)','.end']
    return '\n'.join(rows)+'\n'


def analytic_line(t,source,load):
    z=50.;delay=1.2e-9;rs=50. if load==50 else 10.
    # DC steady state plus the exact causal reflection series. Terms whose
    # arrival is later than the trace contribute zero, with no tail truncation.
    gs=(rs-z)/(rs+z);gl=(load-z)/(load+z)
    result=np.full(len(t),source[0]*load/(rs+load))
    for k in range(int(t[-1]/(2*delay))+2):
        result += z/(rs+z)*(1+gl)*(gs*gl)**k*(np.interp(t-(2*k+1)*delay,t,source)-source[0])
    return result


def calibrated(w,h,load):
    t=w[:,1]
    if not np.isfinite(w).all() or t[0]>1e-15 or t[-1]<12e-9-1e-12 or np.any(np.diff(t)<=0):raise ValueError('Incomplete passive calibration')
    ref=w[:,h['V(OUT_T)']];candidate=w[:,h['V(OUT_O)']]
    error=float(np.max(abs(ref-candidate)))
    expected=analytic_line(t,w[:,h['V(SRC)']],load)
    analytic=float(np.max(abs(candidate-expected)));ref_error=float(np.max(abs(ref-expected)))
    return dict(passed=max(error,analytic,ref_error)<=.001,max_t_ltra_error_v=error,
        max_ltra_analytic_error_v=analytic,max_t_analytic_error_v=ref_error,limit_v=.001,qualified_phy=False)


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/tx_convergence_isolation') or parent.name!='coupled_raw':raise ValueError('Use original coupled raw-TX-RC failure')
    r=json.loads((parent/'summary.json').read_text());m=json.loads((parent.parent/'manifest.json').read_text())
    if r.get('numerically_completed') is not False or 'Timestep too small' not in (r.get('failure') or '') or r['manifest_sha256']!=sha(parent.parent/'manifest.json'):raise ValueError('Require bound terminal coupled abort')
    for n,h in r['files'].items():
        if sha(parent/n)!=h:raise ValueError('Original terminal output changed')
    for n,h in m['identity']['inputs'].items():
        if sha(ROOT/n)!=h:raise ValueError('Original model/input changed')
    paths=[parent.parent/'manifest.json']+[parent/n for n in ['summary.json','bench.cir','library.spice']]
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in ['isolate_channel_model.py','run_ngspice.py','dll_measurements.py','spice_engine.py','spice_dispatch.py','reduce_rc.py','dll_campaign.py','receiver_static_diagnosis.py']},simulator=provenance(),
        scope='Channel isolation only. Original devices/RC, bias, package L/C, termination, stimuli and solver accuracy remain intact. Zero delay is a localization control; lossless LTRA preserves analytic impedance/delay and requires passive calibration. Neither case admits a circuit or PHY.',
        documentation='https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf')
    out=ROOT/'build/diagnostics/channel_model_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    tasks=[]
    for mode in CASES:
        folder=out/mode;folder.mkdir(exist_ok=True);deck,ports=fixture((parent/'bench.cir').read_text(),parent,folder,mode)
        for n,body in [('bench.cir',deck),('library.spice',(parent/'library.spice').read_text())]:
            p=folder/n
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared channel fixture changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(id=mode,ports=ports,files={n:sha(folder/n) for n in ['bench.cir','library.spice']}))
    controls=[]
    for load in [25,50,100]:
        folder=out/('calibration_'+str(load));folder.mkdir(exist_ok=True);p=folder/'bench.cir';body=calibration(load)
        if p.exists() and p.read_text()!=body:raise ValueError('Prepared calibration changed')
        if not p.exists():p.write_text(body)
        controls.append(dict(id=folder.name,load_ohm=load,source_ohm=50 if load==50 else 10,files={'bench.cir':sha(p)}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,calibrations=controls,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/channel_model_isolation'):raise ValueError('Use prepared channel isolation')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    if [t['id'] for t in m['tasks']]!=CASES or [c['load_ohm'] for c in m['calibrations']]!=[25,50,100]:raise ValueError('Incomplete channel-control coverage')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Channel context changed')
    def execute(task,control=False):
        folder=out/task['id'];unchanged()
        if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Channel fixture changed')
        if any((folder/n).exists() for n in ['bench.raw','ngspice.log','summary.json']):raise ValueError('Prior channel output retained')
        atomic(folder/'state.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='channel_'+task['id']):
            unchanged();atomic(folder/'state.json',dict(status='running',qualified_phy=False))
            p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();complete=False;metrics=None
        if p.returncode==0:
            names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]
            complete=bool(np.isfinite(w).all() and t[0]<=1e-15 and t[-1]>=12e-9-1e-12 and np.all(np.diff(t)>0))
            if control:
                wave,h=read_wave(folder/'bench.cir.prn');metrics=calibrated(wave,h,task['load_ohm'])
        log=(folder/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
        result=dict(task=task['id'],numerically_completed=complete,metrics=metrics,returncode=p.returncode,failure=failure[0] if failure else None,
            manifest_sha256=stamp,electrical_verdict=None,qualified_phy=False,files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
        capture_manifest(folder/'summary.json',result);atomic(folder/'state.json',dict(status='completed_diagnostic',qualified_phy=False));return result
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior channel campaign retained')
        atomic(out/'state.json',dict(status='calibrating_line_models',qualified_phy=False))
        controls=[execute(c,True) for c in m['calibrations']]
        if any(not c['numerically_completed'] or not c['metrics'] or c['metrics']['passed'] is not True for c in controls):
            capture_manifest(out/'summary.json',dict(calibrations=controls,qualified_phy=False,status='held_calibration_failed',manifest_sha256=stamp))
            atomic(out/'state.json',dict(status='held_calibration_failed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='running_channel_controls',qualified_phy=False))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,m['tasks']))
        capture_manifest(out/'summary.json',dict(calibrations=controls,results=results,qualified_phy=False,manifest_sha256=stamp,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
