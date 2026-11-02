#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test two real restoration tapers after the completed ideal-gate causal control."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
import driver_gate_taper as circuit
import isolate_driver_balance as reference
from dll_campaign import atomic
from dll_measurements import read_wave,average
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command,engine,provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
sha=reference.sha
EXTRA=['XD:XCORE:XLS:'+n for n in ['L','R','G0_0','G0_1','G1_0','G1_1']]


def prerequisites(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/driver_balance_isolation'):raise ValueError('Use original driver balance controls')
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];stamp=sha(parent/'manifest.json')
    if parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or provenance()!=i['simulator']:raise ValueError('Balance context/runtime changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Balance input/producer changed')
    paths=[parent/'manifest.json'];results={}
    for name in ['baseline','balanced_100ps']:
        task=next(t for t in m['tasks'] if t['id']==name);folder=parent/name
        r=json.loads((folder/'summary.json').read_text())
        if r.get('returncode')!=0 or r.get('manifest_sha256')!=stamp:raise ValueError('Require complete baseline and ideal control')
        if any(sha(folder/n)!=h for n,h in dict(task['files'],**r['files']).items()):raise ValueError('Completed balance proof changed')
        measured=reference.measure(*read_wave(folder/'bench.cir.prn'))
        if measured!=r['metrics']:raise ValueError('Balance waveform remeasurement changed')
        results[name]=measured;paths += [folder/n for n in set(task['files'])|set(r['files'])|{'summary.json'}]
    a,b=results['baseline'],results['balanced_100ps']
    if b['rising_output_edges']!=a['rising_output_edges'] or a['rising_output_edges']!=22 or b['common_mode_pp_v']>=.5*a['common_mode_pp_v']:raise ValueError('Ideal control does not support gate-drive experiment')
    return m,paths,results


def fixture(deck,old,new,source):
    include=f'.include "{old}/source.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 80n 0 1p']:raise ValueError('Require original 80 ns/1 ps baseline fixture')
    result=deck.replace(include,f'.include "{new}/source.spice"');prints=re.findall(r'(?im)^\.print tran[^\n]+',result)
    if len(prints)!=1 or '.save ' in result:raise ValueError('Unexpected baseline observations')
    result=result.replace(prints[0],prints[0]+' '+' '.join('V('+n+')' for n in EXTRA))
    # ngspice retains these branch currents in raw data; the original exporter
    # still writes its ordered voltage-only .prn columns for shared analyzers.
    result=result.replace('.end\n','.save i(VIO) i(VDIG)\n.end\n')
    ProbeNetwork(source).validate(result,re.findall(r'V\(([^)]+)\)',re.search(r'(?im)^\.print tran[^\n]+',result)[0]))
    return result


def added_stress(w,h,counts):
    v=lambda n:w[:,h['V('+n+')']];rows=[]
    for branch,inn,out in [(0,'L','DP'),(1,'R','DN')]:
        chain=['XD:XCORE:XLS:'+inn,f'XD:XCORE:XLS:G{branch}_0',f'XD:XCORE:XLS:G{branch}_1','XD:XCORE:'+out]
        for stage,count in enumerate(counts):
            gate,drain=v(chain[stage]),v(chain[stage+1])
            for polarity,rail in [('p',3.3),('n',0.)]:
                rows.append(dict(branch=branch,stage=stage,polarity=polarity,parallel_devices=count,
                    max_abs_vgs=float(np.max(abs(gate-rail))),max_abs_vgd=float(np.max(abs(gate-drain))),
                    max_abs_vds=float(np.max(abs(drain-rail))),max_abs_vbs=0.))
    return rows


def measure(folder,variant):
    w,h=read_wave(folder/'bench.cir.prn');metrics=reference.measure(w,h);names,raw=read_raw(folder/'bench.raw');t=raw[:,names.index('time')]
    if not np.isfinite(raw).all() or not np.array_equal(t,w[:,1]):raise ValueError('Taper raw/export samples invalid or times differ')
    window=(t>20e-9)&(t<75e-9);at=np.r_[20e-9,t[window],75e-9];power={}
    for rail,voltage,name in [('io',3.3,'i(vio)'),('digital',1.8,'i(vdig)')]:
        if name not in names:raise ValueError('Missing real supply-current observation '+name)
        power[rail]=float(-voltage*average(at,np.interp(at,t,raw[:,names.index(name)])))
    metrics.update(added_mos_stress=added_stress(w,h,circuit.VARIANTS[variant]),mean_supply_power_w=power,
        scope='Source TT25 diagnostic only; added-device voltages and real supply currents observed. Full source PVT/DC/waveform, extracted loading and all qualification gates remain required.')
    return metrics


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Use pinned ngspice')
    m,paths,proof=prerequisites(parent);previous=m['identity']
    identity=dict(parent=str(parent.relative_to(ROOT)),reference=proof,inputs={**previous['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        code={**previous['code'],**{n:sha(ROOT/'scripts'/n) for n in ['driver_gate_taper.py','probe_driver_gate_taper.py','spice_probes.py']}},simulator=provenance(),
        scope='Two bounded real-MOS three-stage restoration tapers, original polarity, same 110:1 driver bridge/CMFB/load/rails, original 80 ns TT25 source fixture. Supported by remeasured baseline and 100 ps ideal-gate control. Slower ideal control continues independently. No source PVT, physical or hardware selection, generator compliance or PHY admission.')
    out=ROOT/'build/diagnostics/driver_gate_taper'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True);tasks=[]
    old=parent/'baseline';base=(old/'source.spice').read_text()
    for variant in circuit.VARIANTS:
        folder=out/variant;folder.mkdir(exist_ok=True);source=circuit.transform(base,variant);deck=fixture((old/'bench.cir').read_text(),old,folder,source)
        for n,text in [('source.spice',source),('bench.cir',deck)]:
            p=folder/n
            if p.exists() and p.read_text()!=text:raise ValueError('Prepared taper changed')
            if not p.exists():p.write_text(text)
        tasks.append(dict(id=variant,files={n:sha(folder/n) for n in ['source.spice','bench.cir']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_gate_taper'):raise ValueError('Use prepared real-MOS taper experiment')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items())):raise ValueError('Gate taper context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if [t['id'] for t in m['tasks']]!=list(circuit.VARIANTS):raise ValueError('Incomplete taper coverage')
        if (out/'state.json').exists():raise ValueError('Prior taper experiment retained')
        results=[]
        for task in m['tasks']:
            folder=out/task['id']
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Taper fixture changed')
            if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log','summary.json']):raise ValueError('Partial taper output retained')
            atomic(out/'state.json',dict(status='waiting_'+task['id'],qualified_phy=False))
            with lease(ROOT,priority=2,label=task['id']):
                unchanged();atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();metrics=measure(folder,task['id']) if p.returncode==0 else None
            r=dict(task=task['id'],returncode=p.returncode,metrics=metrics,qualified_phy=False,manifest_sha256=stamp,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',r);results.append(r)
            if metrics is None:break
        complete=len(results)==2 and all(r['metrics'] is not None for r in results)
        capture_manifest(out/'summary.json',dict(results=results,diagnostic_complete=complete,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic' if complete else 'held_numerical_failure',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
