#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded conditioner-before-mux test after measured 45 ps front-end bias."""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
import os
from pathlib import Path
import numpy as np
import probe_tag_arbiter_v2 as original

base=original.base
ROOT=original.ROOT
VERSION='conditioner-before-swap-tag-arbiter-v2.1'


def circuit(drive):
    text=original.circuit(drive)
    changes={
        'Xra R F SW VSS VSS VDD VDD r0 sky130_fd_sc_hd__mux2_1':'Xra r0 f0 SW VSS VSS VDD VDD a sky130_fd_sc_hd__mux2_1',
        'Xfb F R SW VSS VSS VDD VDD f0 sky130_fd_sc_hd__mux2_1':'Xfb f0 r0 SW VSS VSS VDD VDD b sky130_fd_sc_hd__mux2_1',
        f'Xab r0 VSS VSS VDD VDD a sky130_fd_sc_hd__buf_{drive}':f'Xab R VSS VSS VDD VDD r0 sky130_fd_sc_hd__buf_{drive}',
        f'Xbb f0 VSS VSS VDD VDD b sky130_fd_sc_hd__buf_{drive}':f'Xbb F VSS VSS VDD VDD f0 sky130_fd_sc_hd__buf_{drive}'}
    for old,new in changes.items():
        if text.count(old)!=1:raise ValueError('Original conditioner topology changed')
        text=text.replace(old,new)
    return text


def fixture(out,spec):
    text=original.fixture(out,spec)
    return text.replace('V(XD:oa) V(XD:ob)','V(XD:oa) V(XD:ob) V(XD:r0) V(XD:f0)')


def measure(folder,spec):
    result=original.measure(folder,spec)
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    offsets=[]
    for cycle in range(4):
        mask=(t>=cycle*10000+1500)&(t<cycle*10000+5000)
        a=base.crossings(t[mask],w[mask,names.index('v(xd.r0)')]);b=base.crossings(t[mask],w[mask,names.index('v(xd.f0)')])
        if len(a)!=1 or len(b)!=1:raise ValueError('Missing first-stage conditioned event')
        offsets.append(float(b[0]-a[0]))
    return dict(result,first_stage_feedback_minus_reference_ps=offsets)


def prepare(parent):
    pm=original.bound(parent)
    files=[Path(__file__),ROOT/'scripts/probe_tag_arbiter_v2.py',ROOT/'sky130/v2/openlvds_preconditioned_arbiter_v2.v',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(drive=d,swap=0,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf)
        for d,o,(sr,sf) in itertools.product([1,4],[-20,20],[(20,200),(200,20)])]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},
        pdk=pm['identity']['pdk'],pdk_sha256=pm['identity']['pdk_sha256'],
        model_library=pm['identity']['model_library'],model_library_sha256=pm['identity']['model_library_sha256'],
        parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=base.sha(parent/'manifest.json'),
        simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/preconditioned_arbiter_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);base.write(out/'cells.spice',(parent/'cells.spice').read_text())
    for drive in [1,4]:base.write(out/f'arbiter{drive}.spice',circuit(drive))
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/preconditioned_arbiter_v2'):raise ValueError('Wrong preconditioned context')
    m=original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']
        or base.sha(Path(i['model_library']))!=i['model_library_sha256']):
        raise ValueError('Preconditioner context changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure;base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
