#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded smooth-source numerical diagnostic for the unchanged DCDL topology.

Original piecewise-linear full-fine case hit a timestep collapse at the input
fall corner. This independent fixture keeps fixed supplies and a 160 ps input
10--90% slew, using analytic transitions with continuous derivatives. Results
from different source wave shapes must not be mixed into one legal-code table.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import probe_digital_dcdl_v2 as original

ROOT=original.ROOT
h=original.helpers
VERSION='source-digital-dcdl-smooth-diagnostic-v2.1'


def prepare(parent):
    m=original.bound(parent)
    selected=[s for s in m['identity']['specs'] if s['coarse'] in (0,1) and s['fine'] in (0,31)]
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'sky130/v2/openlvds_dcdl_v2.v',ROOT/'clocking_v2.json']
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=h.sha(parent/'manifest.json'),
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],simulator=h.provenance(),specs=selected,
        input_source='analytic_tanh_160ps_10_90',tau_ps=72.81913813014699)
    out=ROOT/'build/diagnostics/digital_dcdl_smooth_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);h.write(out/'cells.spice',(parent/'cells.spice').read_text());tasks=[]
    for n,spec in enumerate(selected):
        lib=f'dcdl_{n}.spice';h.write(out/lib,original.circuit(16,32,spec['coarse'],spec['fine']))
        folder=out/str(n);folder.mkdir()
        deck=original.fixture(out,spec,lib)
        old='VIN IN 0 PWL(0 0 2n 0 2.2n 1.8 20n 1.8 20.2n 0)'
        if deck.count(old)!=1:raise ValueError('Original stimulus changed')
        deck=deck.replace(old,'BIN IN 0 V={0.9*(tanh((time-2.1n)/72.819138130147p)-tanh((time-20.1n)/72.819138130147p))}')
        h.write(folder/'bench.cir',deck);tasks.append(dict(id=str(n),spec=spec,deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcdl_smooth_v2'):raise ValueError('Wrong smooth-source context')
    m=h.bound(out);i=m['identity']
    if i['version']!=VERSION or h.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']:
        raise ValueError('Smooth-source context changed')
    return m

@contextmanager
def profile():
    previous=original.bound;original.bound=bound
    try:yield
    finally:original.bound=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():original.run(a.artifact.resolve())
