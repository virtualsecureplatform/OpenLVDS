#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Audit captured OpenPLL edge traces against the current frequency/duty contract without regenerating them."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import numpy as np
import openpll_clock as original
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
METRICS=['frequency_mhz','duty_min','duty_max','period_jitter_pp_ps','rising_edges']


def metrics(edges,requirements):
    a=np.asarray(edges,dtype=float)
    if (a.ndim!=2 or a.shape[1]!=2 or len(a)<16 or not np.isfinite(a).all() or
        np.any(np.diff(a[:,0])<=0) or not np.isin(a[:,1],[0,1]).all() or np.any(np.diff(a[:,1])==0)):
        raise ValueError('Require finite strictly timed alternating binary clock edges')
    result=original.stats(a[:,0],a[:,1])
    low,high=min(requirements['clock_test_mhz']),max(requirements['clock_test_mhz'])
    duty_low,duty_high=min(requirements['clock_duty']),max(requirements['clock_duty'])
    # The archived physical CSV is rounded to 1e-9 ns. These tolerances cover
    # that serialization and floating point boundary arithmetic, not jitter.
    result['passed']=bool(low-1e-6<=result['frequency_mhz']<=high+1e-6 and
        result['duty_min']>=duty_low-1e-9 and result['duty_max']<=duty_high+1e-9)
    return result


def physical_edges(path):
    rows=[]
    for line in path.read_text().splitlines():
        try:rows.append(list(map(float,line.split())))
        except ValueError:continue
    w=np.asarray(rows,dtype=float)
    if w.ndim!=2 or w.shape[1]<3 or len(w)<2 or not np.isfinite(w).all() or np.any(np.diff(w[:,1])<=0):
        raise ValueError('Require a complete finite monotonic archived physical waveform')
    t=w[:,1]*1e9;v=w[:,2]-.9;i=np.where(v[:-1]*v[1:]<0)[0]
    times=t[i]-v[i]*(t[i+1]-t[i])/(v[i+1]-v[i]);levels=(v[i+1]>0).astype(int)
    keep=times>t[-1]*.4
    return times[keep],levels[keep]


def verify():
    req=json.loads((ROOT/'requirements.json').read_text());folder=ROOT/'build/openpll'
    commit=subprocess.run(['git','-C',str(ROOT/'thirdparties/OpenPLL'),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    if commit!=req['openpll_commit']:raise ValueError('OpenPLL checkout differs from the required pin')
    paths=[ROOT/'requirements.json',Path(__file__),ROOT/'scripts/openpll_clock.py',ROOT/'scripts/receiver_static_diagnosis.py']
    sources=original.rtl_sources();paths+=sources;results=[]
    for kind,summary_name,csv_name in [('rtl','summary.json','clock.csv'),('physical','physical_summary.json','physical_clock.csv')]:
        report=folder/summary_name;csv=folder/csv_name;saved=json.loads(report.read_text());paths += [report,csv]
        if saved.get('passed') is not True or saved.get('clock_sha256')!=sha(csv):raise ValueError('Legacy clock report failed or its edge trace changed')
        edges=np.loadtxt(csv,delimiter=',',skiprows=1)
        checked=metrics(edges,req)
        if kind=='rtl':
            stamp=hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()
            if saved.get('source_sha256')!=stamp or saved.get('pdk_pin')!=req['pdk_version']:raise ValueError('OpenPLL RTL source or PDK fingerprint changed')
            legacy=original.stats(edges[:,0],edges[:,1])
        else:
            trace=Path(saved['trace'])
            if trace.is_absolute() or '..' in trace.parts or not trace.is_relative_to('build/openpll'):raise ValueError('Unexpected archived physical waveform path')
            raw=ROOT/trace;paths.append(raw)
            if saved.get('input_sha256')!=sha(raw):raise ValueError('Archived physical waveform changed')
            times,levels=physical_edges(raw);legacy=original.stats(times,levels)
            text=io.StringIO();np.savetxt(text,np.column_stack([times-times[0],levels]),delimiter=',',header='time_ns,level',comments='',fmt=['%.9f','%d'])
            if text.getvalue().encode()!=csv.read_bytes():raise ValueError('Physical edge CSV differs from the original full-waveform conversion')
        if any(legacy[k]!=saved[k] for k in METRICS) or legacy['passed']!=saved['passed']:raise ValueError('Original clock measurement changed')
        results.append(dict(kind=kind,trace=str(csv.relative_to(ROOT)),metrics=checked,legacy_metrics_verified=True,source_kind=saved['kind']))
    identity=dict(openpll_commit=commit,files={str(p.relative_to(ROOT)):sha(p) for p in paths},
        contract=dict(frequency_mhz=[min(req['clock_test_mhz']),max(req['clock_test_mhz'])],duty=[min(req['clock_duty']),max(req['clock_duty'])]))
    if any(sha(ROOT/n)!=h for n,h in identity['files'].items()):raise ValueError('Clock audit context changed')
    out=ROOT/'build/diagnostics/openpll_current_contract'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'summary.json',dict(identity=identity,results=results,passed=all(r['metrics']['passed'] for r in results),qualified_phy=False,
        scope='Read-only current frequency/duty contract for exact captured pinned OpenPLL RTL/controller and fixed-code extracted DCO traces. Period jitter is measured, not a closed-loop physical jitter qualification. Original summaries and producer remain untouched; no PHY or link admission.'))
    return out


if __name__=='__main__':print(verify()/'summary.json',flush=True)
