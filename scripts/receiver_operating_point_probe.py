#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Probe source receiver current and BSIM tail parameters at unchanged static input points."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic
import receiver_scaled_decision_experiment as source
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from rx_candidate_aperture import lease
from spice_engine import engine,provenance

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
TAIL='@m.xr.xcore.xct.msky130_fd_pr__nfet_01v8'
NODES=['P','N','Q','XR:XCORE:PP','XR:XCORE:PN','XR:XCORE:CO','XR:XCORE:CL','XR:XCORE:CT','XR:XCORE:NBC']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def operating_deck(deck,parent,out,points):
    include=f'.include "{parent}/source.spice"'
    if deck.count(include)!=1:raise ValueError('Expected the exact source library binding')
    deck=deck.replace(include,f'.include "{out}/source.spice"')
    for name,node,value in [('VP','P',0),('VN','N',.1)]:
        deck,count=re.subn(r'(?m)^'+name+' '+node+r' 0 PWL\([^\n]+\)$',f'{name} {node} 0 {value:g}',deck)
        if count!=1:raise ValueError('Expected the original static input source '+name)
    for row in ['VIO VDDIO 0 3.3','VDIG VDDD 0 1.8','VREF VREF 0 1.2','IREF IREF 0 35u']:
        if not re.search(r'(?m)^'+re.escape(row)+r'\s*$',deck):raise ValueError('Static source rail or reference changed')
    deck=re.sub(r'(?im)^\.options\s+device\s+temp=(\S+)',r'.temp \1',deck)
    deck=re.sub(r'(?im)^\.options\s+timeint\s+',r'.options ',deck)
    deck,count=re.subn(r'(?im)^\.tran[^\n]*\n','',deck)
    if count!=1:raise ValueError('Expected one original static transient')
    saves=['v('+n.replace(':','.').lower()+')' for n in NODES]+['i(vio)','i(vdig)','i(vref)']
    saves.extend(TAIL+'['+field+']' for field in ['id','gm','gds','vdsat'])
    deck,count=re.subn(r'(?im)^\.print tran[^\n]*$',lambda _:'.save '+' '.join(saves),deck)
    if count!=1:raise ValueError('Expected one original static observation command')
    commands=['.control','set filetype=binary','set noaskquit']
    for index,point in enumerate(points):
        commands.extend([f'alter VP = {point["p_v"]:.17g}',f'alter VN = {point["n_v"]:.17g}','op'])
        commands.extend('let tail_'+field+' = '+TAIL+'['+field+']' for field in ['id','gm','gds','vdsat'])
        commands.append(f'write point_{index}.raw all')
    commands.extend(['quit','.endc','.end'])
    deck,count=re.subn(r'(?im)^\.end\s*$',lambda _:'\n'.join(commands),deck)
    if count!=1:raise ValueError('Expected one original deck termination')
    first,rest=deck.split('\n',1)
    return first+'\n.options klu\n'+rest


def prepare(parent,all_points=False):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_scaled_decision_static'):
        raise ValueError('Use a completed uniformly scaled source static case')
    if not (parent/'summary.json').exists():raise ValueError('Complete the source static case first')
    report=source.run(parent)
    if report['scaled_decision']['metrics']['passed'] is not True:raise ValueError('Source static case failed')
    original=json.loads((parent/'manifest.json').read_text());samples=report['scaled_decision']['samples']
    points=[dict(time_ns=s['time_ns'],p_v=s['values']['V(P)'],n_v=s['values']['V(N)'],expected=s['values'])
        for i,s in enumerate(samples) if all_points or i in [0,10]]
    identity=dict(parent=str(parent.relative_to(ROOT)),points=points,simulator_provenance=provenance(),
        code={n:digest(ROOT/'scripts'/n) for n in set(original['identity']['code'])|{NAME,'run_ngspice.py','rx_candidate_aperture.py'}},
        inputs=dict(original['identity']['inputs'],**{str((parent/n).relative_to(ROOT)):digest(parent/n)
            for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']}))
    out=ROOT/'build/diagnostics/receiver_operating_points'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    for name,text in [('source.spice',(parent/'source.spice').read_text()),('bench.cir',operating_deck((parent/'bench.cir').read_text(),parent,out,points))]:
        path=out/name
        if path.exists() and path.read_text()!=text:raise ValueError('Operating-point fixture changed')
        if not path.exists():path.write_text(text)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False,files={n:digest(out/n) for n in ['source.spice','bench.cir']}))
    return out


def measure(folder,points):
    results=[]
    for i,point in enumerate(points):
        names,wave=read_raw(folder/f'point_{i}.raw')
        if wave.shape[0]!=1 or not np.isfinite(wave).all():raise ValueError('Incomplete real operating point')
        values=dict(zip(names,wave[0]));required=['tail_id','tail_gm','tail_gds','tail_vdsat','i(vio)','i(vdig)','i(vref)']
        if any(n not in values for n in required):raise ValueError('Missing requested model/current operating-point vectors')
        if abs(values['v(p)']-point['p_v'])>1e-8 or abs(values['v(n)']-point['n_v'])>1e-8:
            raise ValueError('Operating point input differs from the original static sample')
        differences={n:float(values['v('+n.replace(':','.').lower()+')']-point['expected']['V('+n+')']) for n in NODES}
        power=dict(rails_mw=float((-3.3*values['i(vio)']-1.8*values['i(vdig)'])*1e3),
            reference_mw=float(-1.2*values['i(vref)']*1e3))
        results.append(dict(time_ns=point['time_ns'],voltage_differences_from_transient_v=differences,
            tail={k:float(values['tail_'+k]) for k in ['id','gm','gds','vdsat']},power=power,
            waveform_sha256=digest(folder/f'point_{i}.raw')))
    return results


def run(folder,wait_slot=None):
    if not folder.is_relative_to(ROOT/'build/diagnostics/receiver_operating_points'):raise ValueError('Use a prepared source operating-point probe')
    manifest=json.loads((folder/'manifest.json').read_text());identity=manifest['identity'];stamp=digest(folder/'manifest.json')
    if [p['time_ns'] for p in identity['points']] not in [[10,130],list(range(10,144,12))]:
        raise ValueError('Expected original low/high or all twelve settled input points')
    def unchanged():
        if (digest(folder/'manifest.json')!=stamp or provenance()!=identity['simulator_provenance'] or
                any(digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items()) or
                any(digest(ROOT/n)!=sha for n,sha in identity['inputs'].items()) or
                any(digest(folder/n)!=sha for n,sha in manifest['files'].items())):raise ValueError('Operating-point context changed')
        parent=ROOT/identity['parent']
        if ((folder/'source.spice').read_text()!=(parent/'source.spice').read_text() or
                (folder/'bench.cir').read_text()!=operating_deck((parent/'bench.cir').read_text(),parent,folder,identity['points'])):
            raise ValueError('Operating point differs from the declared unchanged source fixture')
    with (folder/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        cached=json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
        try:
            if cached is None:
                if (folder/'ngspice.log').exists() or list(folder.glob('point_*.raw')):raise ValueError('Partial operating-point evidence retained; use a fresh retry context')
                capture_manifest(folder/'scheduling.json',dict(wait_slot=wait_slot,global_slot_budget=6,manifest_sha256=stamp))
                atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                with lease(wait_slot):
                    unchanged();runtime=ROOT/'build/tools/ngspice-runtime';binary=ROOT/'build/tools/ngspice-root/usr/bin/ngspice'
                    runtime_manifest=json.loads((ROOT/'build/tools/ngspice.json').read_text())
                    if any(digest(ROOT/n)!=sha for n,sha in runtime_manifest['files'].items()):raise ValueError('Changed pinned ngspice runtime')
                    atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                    process=subprocess.run([str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(binary),'-n','-b','-o',str(folder/'ngspice.log'),str(folder/'bench.cir')],cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            results=measure(folder,identity['points']);unchanged()
            result=dict(diagnostic_complete=True,qualified_phy=False,manifest_sha256=stamp,results=results,
                scope='Original source static input points, fixed supplies; model/current capability probe only, not dynamic/native/all-PVT qualification')
            if cached is not None and cached!=result:raise ValueError('Operating-point analysis differs from cached evidence')
            capture_manifest(folder/'summary.json',result)
            atomic(folder/'execution.json',dict(status='completed',qualified_phy=False))
        except Exception as error:
            atomic(folder/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)));raise
    print(folder/'summary.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--all-static-points',action='store_true');parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve(),args.all_static_points),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
