#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native tagged regenerative arbiter pilot after the FF sampler dead zone.

Pulse high widths equal a 400 MHz half-cycle; tags are isolated by 10 ns so
management can retain/read/reset each event. This is a calibration topology,
not a replacement ideal PHY clock. Four pilot tags grant no DLL qualification.
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
VERSION='tagged-regenerative-phase-arbiter-v2.1'


def circuit(drive):
    if drive not in (1,4):raise ValueError('Undeclared conditioning strength')
    return ('.subckt tag_arbiter R F SW ARM QA QB VDD VSS\n'
        'Xra R F SW VSS VSS VDD VDD r0 sky130_fd_sc_hd__mux2_1\n'
        'Xfb F R SW VSS VSS VDD VDD f0 sky130_fd_sc_hd__mux2_1\n'
        f'Xab r0 VSS VSS VDD VDD a sky130_fd_sc_hd__buf_{drive}\n'
        f'Xbb f0 VSS VSS VDD VDD b sky130_fd_sc_hd__buf_{drive}\n'
        'Xora a ha VSS VSS VDD VDD oa sky130_fd_sc_hd__or2_1\n'
        'Xorb b hb VSS VSS VDD VDD ob sky130_fd_sc_hd__or2_1\n'
        'Xha oa ARM VSS VSS VDD VDD ha sky130_fd_sc_hd__and2_1\n'
        'Xhb ob ARM VSS VSS VDD VDD hb sky130_fd_sc_hd__and2_1\n'
        'Xqa ha QB VSS VSS VDD VDD QA sky130_fd_sc_hd__nand2_4\n'
        'Xqb hb QA VSS VSS VDD VDD QB sky130_fd_sc_hd__nand2_4\n.ends tag_arbiter\n')


def fixture(out,spec):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    sr=spec['reference_slew_ps']/1000;sf=spec['feedback_slew_ps']/1000
    delay=2+sr/2-sf/2+spec['offset_ps']/1000
    return (f'OpenLVDS {VERSION}\n.lib "{model}" ss\n.include "{out}/cells.spice"\n'
        f'.include "{out}/arbiter{spec["drive"]}.spice"\n.options device temp=40\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        f'VSW SW 0 {1.8*spec["swap"]}\n'
        'VARM ARM 0 PULSE(0 1.8 1n 20p 20p 5.98n 10n)\n'
        f'VR R 0 PULSE(0 1.8 2n {sr}n {sr}n {1.25-sr}n 10n)\n'
        f'VF F 0 PULSE(0 1.8 {delay}n {sf}n {sf}n {1.25-sf}n 10n)\n'
        'XD R F SW ARM QA QB VDD 0 tag_arbiter\nCQA QA 0 5f\nCQB QB 0 5f\n'
        '.tran 1p 42n 0 1p\n.print tran V(R) V(F) V(ARM) V(QA) V(QB) V(XD:a) V(XD:b) '
        'V(XD:ha) V(XD:hb) V(XD:oa) V(XD:ob) V(VDD)\n.end\n')


def measure(folder,spec):
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1]<41999.99:raise ValueError('Incomplete tagged arbiter trace')
    get=lambda n:w[:,names.index('v('+n+')')]
    votes=[];analog=[];levels=[];conditioned=[]
    for cycle in range(4):
        base_ps=cycle*10000;when=base_ps+6000
        held=[float(np.interp(when,t,get('xd.'+n))) for n in ['ha','hb']]
        if min(held)<1.62:raise ValueError('Missing retained tag')
        reset=[float(np.interp(base_ps+9000,t,get('xd.'+n))) for n in ['ha','hb']] if cycle<3 else None
        if reset is not None and max(reset)>.18:raise ValueError('Tags did not clear before rearm')
        a=float(np.interp(when,t,get('qa')));b=float(np.interp(when,t,get('qb')))
        if spec['swap']:a,b=b,a
        state=lambda v:0 if v<=.18 else (1 if v>=1.62 else None)
        pair=(state(a),state(b));analog.append([a,b]);levels.append(held)
        votes.append(1 if pair==(0,1) else (-1 if pair==(1,0) else (None if None in pair else 0)))
        mask=(t>=base_ps+1500)&(t<base_ps+5000)
        ea=base.crossings(t[mask],get('xd.a')[mask]);eb=base.crossings(t[mask],get('xd.b')[mask])
        if len(ea)!=1 or len(eb)!=1:raise ValueError('Missing/extra conditioned input event')
        conditioned.append(float((eb[0]-ea[0])*(-1 if spec['swap'] else 1)))
    expected=1 if spec['offset_ps']>0 else (-1 if spec['offset_ps']<0 else 0)
    return dict(votes=votes,settled_output_voltages_v=analog,held_tag_voltages_v=levels,
        conditioned_feedback_minus_reference_ps=conditioned,
        correct_sign_fraction=sum(v==expected for v in votes)/len(votes) if expected else None,
        ambiguous_fraction=sum(v==0 for v in votes)/len(votes),unresolved_fraction=sum(v is None for v in votes)/len(votes),
        qualified_phy=False,detector_admitted=False,
        scope='Four isolated native tagged races; no 64-vote, epoch, all-PVT, terminal-stress, physical or PHY admission')


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    files=[Path(__file__),ROOT/'sky130/v2/openlvds_tag_arbiter_v2.v',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(drive=d,swap=s,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf)
        for d,s,o,(sr,sf) in itertools.product([1,4],[0,1],[-150,-20,0,20,150],[(100,100),(20,200),(200,20)])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},pdk=str(pdk),pdk_sha256=base.sha(pdk),
        model_library=str(model),model_library_sha256=base.sha(model),simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/tag_arbiter_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();cells=''
    for name in ['mux2_1','buf_1','buf_4','or2_1','and2_1','nand2_4']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+name)
        cells+=found[0]+'\n'
    base.write(out/'cells.spice',cells)
    for drive in [1,4]:base.write(out/f'arbiter{drive}.spice',circuit(drive))
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tag_arbiter_v2'):raise ValueError('Wrong tagged arbiter context')
    m=original_bound(out);i=m['identity']
    if i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']:raise ValueError('Tagged arbiter context changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure;base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Require artifact')
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
