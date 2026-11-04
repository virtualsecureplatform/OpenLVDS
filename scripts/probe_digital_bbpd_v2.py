#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure sign/dead-zone bias of a native exchanged-input edge sampler.

This deliberately tests the unproven +/-20 ps boundary at the difficult SS40
corner before constructing a DLL measurement engine. Twelve pilot votes do not
grant 64-confirmation lock, epoch, physical, all-PVT or PHY admission.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import numpy as np
import probe_digital_dcc_v2 as base

ROOT=base.ROOT
VERSION='digital-edge-sampled-phase-detector-pilot-v2.1'


def circuit(drive):
    if drive not in (1,4):raise ValueError('Undeclared input drive')
    return ('.subckt bbpd R F SW QA QB VDD VSS\n'
        'Xra R F SW VSS VSS VDD VDD r0 sky130_fd_sc_hd__mux2_1\n'
        'Xfb F R SW VSS VSS VDD VDD f0 sky130_fd_sc_hd__mux2_1\n'
        f'Xab r0 VSS VSS VDD VDD a sky130_fd_sc_hd__buf_{drive}\n'
        f'Xbb f0 VSS VSS VDD VDD b sky130_fd_sc_hd__buf_{drive}\n'
        'Xsa a b VSS VSS VDD VDD QA sky130_fd_sc_hd__dfxtp_1\n'
        'Xsb b a VSS VSS VDD VDD QB sky130_fd_sc_hd__dfxtp_1\n.ends bbpd\n')


def fixture(out,spec):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    sr=spec['reference_slew_ps']/1000;sf=spec['feedback_slew_ps']/1000
    delay=2+sr/2-sf/2+spec['offset_ps']/1000
    return (f'OpenLVDS {VERSION}\n.lib "{model}" ss\n.include "{out}/cells.spice"\n'
        f'.include "{out}/pd{spec["drive"]}.spice"\n.options device temp=40\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        f'VSW SW 0 {1.8*spec["swap"]}\n'
        f'VR R 0 PULSE(0 1.8 2n {sr}n {sr}n {1.25-sr}n 2.5n)\n'
        f'VF F 0 PULSE(0 1.8 {delay}n {sf}n {sf}n {1.25-sf}n 2.5n)\n'
        'XD R F SW QA QB VDD 0 bbpd\nCQA QA 0 5f\nCQB QB 0 5f\n'
        '.tran 1p 42n 0 1p\n.print tran V(R) V(F) V(QA) V(QB) V(XD:a) V(XD:b) V(VDD)\n.end\n')


def measure(folder,spec):
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1]<41999.99:raise ValueError('Incomplete phase detector trace')
    get=lambda n:w[:,names.index('v('+n+')')]
    readouts=2000+spec['reference_slew_ps']/2+np.arange(3,15)*2500+2000
    votes=[];analog=[]
    for when in readouts:
        a=float(np.interp(when,t,get('qa')));b=float(np.interp(when,t,get('qb')))
        if spec['swap']:a,b=b,a
        state=lambda v:0 if v<=.18 else (1 if v>=1.62 else None)
        pair=(state(a),state(b));analog.append([a,b])
        votes.append(1 if pair==(0,1) else (-1 if pair==(1,0) else (None if None in pair else 0)))
    expected=1 if spec['offset_ps']>0 else (-1 if spec['offset_ps']<0 else 0)
    return dict(votes=votes,settled_output_voltages_v=analog,
        correct_sign_fraction=sum(v==expected for v in votes)/len(votes) if expected else None,
        ambiguous_fraction=sum(v==0 for v in votes)/len(votes),
        unresolved_fraction=sum(v is None for v in votes)/len(votes),
        qualified_phy=False,detector_admitted=False,
        scope='Native pilot sign/dead-zone samples only; no epoch, PVT, physical, closed-loop or PHY admission')


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    files=[Path(__file__),ROOT/'sky130/v2/openlvds_bbpd_v2.v',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(drive=d,swap=swap,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf)
        for d,swap,o,(sr,sf) in itertools.product([1,4],[0,1],[-150,-20,0,20,150],[(100,100),(20,200),(200,20)])]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},pdk=str(pdk),
        pdk_sha256=base.sha(pdk),model_library=str(model),model_library_sha256=base.sha(model),
        simulator=base.provenance(),specs=specs,process='ss',temperature=40)
    out=ROOT/'build/diagnostics/digital_bbpd_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();cells=''
    for name in ['dfxtp_1','mux2_1','buf_1','buf_4']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+name)
        cells+=found[0]+'\n'
    base.write(out/'cells.spice',cells)
    for d in [1,4]:base.write(out/f'pd{d}.spice',circuit(d))
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_bbpd_v2'):raise ValueError('Wrong phase detector context')
    m=original_bound(out);i=m['identity']
    if i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']:
        raise ValueError('Phase detector context changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure
    base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Require artifact')
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
