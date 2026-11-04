#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Unwrapped single-pulse source characterization of a SKY130 DCDL candidate.

Measures an isolated topology, not a DLL. Range, fine increments and coarse/fine
overlap must be established before spending on a physical implementation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import numpy as np
import probe_digital_dcc_v2 as helpers
from spice_dispatch import lease
from spice_engine import command,provenance
from run_ngspice import read_raw

ROOT=helpers.ROOT
VERSION='source-digital-dcdl-v2.1'
CELLS=('buf_4','nand2_4','nand2b_4','einvp_1')


def circuit(coarse_count,fine_count,coarse,fine):
    if coarse_count not in (16,32,64,128,256) or fine_count not in (16,32):raise ValueError('Undeclared candidate')
    if not 0<=coarse<coarse_count or not 0<=fine<fine_count:raise ValueError('Invalid thermometer code')
    s=['.subckt dcdl_source IN OUT VDD VSS', 'Xin IN VSS VSS VDD VDD f0 sky130_fd_sc_hd__buf_4']
    for i in range(coarse_count):
        enabled='VDD' if i<coarse else 'VSS'
        if i<coarse_count-1:
            s += [f'Xf{i} f{i} {enabled} VSS VSS VDD VDD f{i+1} sky130_fd_sc_hd__nand2_4',
                  f'Xt{i} {enabled} f{i} VSS VSS VDD VDD t{i} sky130_fd_sc_hd__nand2b_4',
                  f'Xp{i} r{i+1} {enabled} VSS VSS VDD VDD p{i} sky130_fd_sc_hd__nand2b_4',
                  f'Xm{i} t{i} p{i} VSS VSS VDD VDD r{i} sky130_fd_sc_hd__nand2_4']
        else:
            s += [f'Xt{i} VSS f{i} VSS VSS VDD VDD t{i} sky130_fd_sc_hd__nand2b_4',
                  f'Xm{i} t{i} VDD VSS VSS VDD VDD r{i} sky130_fd_sc_hd__nand2_4']
    for i in range(fine_count-1):
        node='f0' if i%2==0 else 'r0';enabled='VDD' if i<fine else 'VSS'
        s += [f'Xload{i} {node} {enabled} VSS VSS VDD VDD dummy{i} sky130_fd_sc_hd__einvp_1']
    s += ['Xout r0 VSS VSS VDD VDD OUT sky130_fd_sc_hd__buf_4','.ends dcdl_source']
    return '\n'.join(s)+'\n'


def fixture(out,spec,lib):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION} unwrapped source pulse\n.lib "{model}" {spec["process"]}\n'
        f'.include "{out}/cells.spice"\n.include "{out}/{lib}"\n'
        f'.options device temp={spec["temperature"]}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VDD VDD 0 1.8\nVIN IN 0 PWL(0 0 2n 0 2.2n 1.8 20n 1.8 20.2n 0)\n'
        'XD IN OUT VDD 0 dcdl_source\nCLOAD OUT 0 20f\n'
        '.tran 2p 40n 0 2p\n.print tran V(IN) V(OUT) V(XD:f0) V(XD:r0) V(VDD)\n.end\n')


def measure(folder):
    names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1]<39999.99:raise ValueError('Incomplete DCDL waveform')
    result={}
    for rising,label in [(True,'rise'),(False,'fall')]:
        a=helpers.crossings(t,w[:,names.index('v(in)')],rising)
        b=helpers.crossings(t,w[:,names.index('v(out)')],rising)
        if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra pulse or invalid epoch')
        result[label+'_delay_ps']=float(b[0]-a[0])
        out=w[:,names.index('v(out)')]
        low,high=(.18,1.62) if rising else (1.62,.18)
        def cross(level):
            v=out-.9+level # use helpers threshold .9: threshold(out) = 1.8-level
            return helpers.crossings(t,v,rising)
        # Direct 10--90% crossings on the unique edge.
        def edge(level):
            idx=np.flatnonzero((out[:-1]<level)&(out[1:]>=level) if rising else (out[:-1]>level)&(out[1:]<=level))
            if len(idx)!=1:raise ValueError('Ambiguous output slew')
            i=idx[0];return t[i]+(level-out[i])*(t[i+1]-t[i])/(out[i+1]-out[i])
        result[label+'_slew_ps']=float(abs(edge(high)-edge(low)))
    return dict(**result,qualified_phy=False,scope='Unwrapped source cell delay only; no physical RC or DLL admission')


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'sky130/v2/openlvds_dcdl_v2.v',
        ROOT/'clocking_v2.json',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py']
    codes=[(c,f) for c in (0,1,2) for f in (0,1,16,31)]
    specs=[dict(process='tt',temperature=25,coarse_count=16,fine_count=32,coarse=c,fine=f) for c,f in codes]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):helpers.sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=helpers.sha(pdk),simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/digital_dcdl_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();text=''
    for cell in CELLS:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+cell+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+cell)
        text+=found[0]+'\n'
    helpers.write(out/'cells.spice',text);tasks=[]
    for n,spec in enumerate(specs):
        lib=f'dcdl_{n}.spice';helpers.write(out/lib,circuit(16,32,spec['coarse'],spec['fine']))
        folder=out/str(n);folder.mkdir();helpers.write(folder/'bench.cir',fixture(out,spec,lib))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=helpers.sha(folder/'bench.cir')))
    helpers.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:helpers.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcdl_v2'):raise ValueError('Wrong DCDL context')
    m=helpers.bound(out)
    if m['identity']['version']!=VERSION:raise ValueError('Wrong DCDL version')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior execution')
        helpers.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcdl_v2_'+task['id']):
                    bound(out);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                helpers.write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:helpers.sha(p) for p in folder.iterdir() if p.is_file()})
            helpers.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);helpers.atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        helpers.atomic(out/'state.json',dict(status='source_screen_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Require artifact')
    elif a.action=='run':run(a.artifact.resolve())
    else:print(json.dumps(bound(a.artifact.resolve()),indent=2))
