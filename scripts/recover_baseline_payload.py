#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recover a completed short trace after the frozen wrapper's missing reader import."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
import restore_baseline_coupled as original
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,provenance

ROOT=Path(__file__).resolve().parents[1]
sha=original.sha


def completed_export(folder,stop_ns):
    names,raw=original.channel.read_raw(folder/'bench.raw')
    if not original.complete(names,raw,stop_ns*1e-9):raise ValueError('Incomplete numerical trace')
    wave,headers=original.read_wave(folder/'bench.cir.prn')
    if len(wave)!=len(raw) or not np.array_equal(wave[:,0],np.arange(len(raw))):raise ValueError('Export sample count changed')
    if not np.array_equal(wave[:,1],raw[:,names.index('time')]):raise ValueError('Export time differs from raw trace')
    for name,column in headers.items():
        if not name.startswith('V('):continue
        vector=name.replace(':','.').lower()
        if vector not in names or not np.array_equal(wave[:,column],raw[:,names.index(vector)]):raise ValueError('Export voltage differs from raw trace')
    return wave,headers


def payload_metrics(folder):
    wave,h=completed_export(folder,188.049);t=wave[:,1];v=lambda n:wave[:,h['V('+n+')']]
    rises=original.edge_times(t,v('CLK0'),rising=True);launch=rises[rises>=60e-9][:16]*1e9
    if len(launch)!=16:raise ValueError('Incomplete original 32-bit payload launch clocks')
    return (original.analyze(wave,original.word_stream(16),launch,1000/410),
            original.pulse_transport(t,v('RCP')-v('RCN'),v('RXCLOCK'),60e-9,120e-9))


def prepare(source):
    if not source.is_relative_to(ROOT/'build/diagnostics/baseline_coupled_restoration'):raise ValueError('Use frozen baseline restoration')
    m=original.context(source)
    if provenance()!=m['identity']['simulator']:raise ValueError('Original runtime changed')
    if [(t['id'],t['stop_ns']) for t in m['tasks']]!=[('short',12),('payload',188.049)]:raise ValueError('Original diagnostic coverage changed')
    for task in m['tasks']:
        if any(sha(source/task['id']/n)!=h for n,h in task['files'].items()):raise ValueError('Original fixture changed')
    if (source/'short/summary.json').exists() or (source/'summary.json').exists():raise ValueError('Original result already recorded')
    if json.loads((source/'state.json').read_text()).get('status')!='running_short':raise ValueError('Unexpected frozen execution state')
    if any((source/'payload'/n).exists() for n in ['bench.raw','ngspice.log','console.log','bench.cir.prn','summary.json']):raise ValueError('Original payload output retained')
    completed_export(source/'short',12)
    paths=[source/'manifest.json',source/'state.json']
    paths += [source/t['id']/n for t in m['tasks'] for n in t['files']]
    paths += [source/'short'/n for n in ['bench.raw','bench.cir.prn','bench.ngspice.cir','ngspice.log','console.log']]
    identity=dict(source=str(source.relative_to(ROOT)),inputs={**m['identity']['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        code={**m['identity']['code'],'recover_baseline_payload.py':sha(Path(__file__))},simulator=provenance(),
        scope='Read-only recovery of completed twelve-ns raw/export evidence after the frozen missing-reader-import error. Original producer, fixtures and outputs retained. Fresh unchanged 188.049 ns payload diagnostic only; no short rerun, electrical admission or PHY release.')
    out=ROOT/'build/diagnostics/baseline_payload_recovery'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    old=source/'payload';deck=(old/'bench.cir').read_text();include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1:raise ValueError('Unexpected payload include')
    files={}
    for n,body in [('bench.cir',deck.replace(include,f'.include "{out}/library.spice"')),('library.spice',(old/'library.spice').read_text())]:
        path=out/n
        if path.exists() and path.read_text()!=body:raise ValueError('Recovery fixture changed')
        if not path.exists():path.write_text(body)
        files[n]=sha(path)
    capture_manifest(out/'manifest.json',dict(identity=identity,files=files,qualified_phy=False))
    capture_manifest(out/'short_observation.json',dict(numerically_completed=True,raw_export_agree=True,
        source=str(source.relative_to(ROOT)),manifest_sha256=sha(source/'manifest.json'),electrical_verdict=None,qualified_phy=False))
    return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/baseline_payload_recovery'):raise ValueError('Use prepared payload recovery')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or
                out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
                any(sha(out/n)!=h for n,h in m['files'].items())):raise ValueError('Payload recovery evidence changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if any((out/n).exists() for n in ['state.json','bench.raw','bench.cir.prn','ngspice.log','summary.json']):raise ValueError('Prior recovery output retained')
        atomic(out/'state.json',dict(status='waiting_for_payload_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='baseline_recovered_payload'):
            unchanged();atomic(out/'state.json',dict(status='running_payload',qualified_phy=False))
            p=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(p.stdout+p.stderr);unchanged();numerical=False;metrics=None;transport=None
        if p.returncode==0:
            metrics,transport=payload_metrics(out);numerical=True
        log=(out/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
        capture_manifest(out/'summary.json',dict(numerically_completed=numerical,returncode=p.returncode,metrics=metrics,clock_transport=transport,
            failure=failure[0] if failure else None,manifest_sha256=stamp,electrical_verdict=None,qualified_phy=False,scope=i['scope'],
            files={n:sha(out/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (out/n).exists()}))
        atomic(out/'state.json',dict(status='completed_diagnostic' if numerical else 'held_numerical_failure',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
