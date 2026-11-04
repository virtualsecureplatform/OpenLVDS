#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent stronger-toggle DCC experiment; retain the minimum-drive screen.

Uses the frozen source runner's measurement/lease machinery, with a new bound
circuit, manifest and producer identity. It grants no physical qualification.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import probe_digital_dcc_v2 as base

ROOT=base.ROOT
VERSION='source-digital-dcc-toggle-drive-v2.1'


def circuit(buffers, drive):
    if drive not in (2,4): raise ValueError('Undeclared toggle drive')
    text=base.circuit(buffers)
    text=text.replace('Xinv Q VSS VSS VDD VDD feedback sky130_fd_sc_hd__inv_1',
        f'Xinv QT VSS VSS VDD VDD feedback sky130_fd_sc_hd__inv_{drive}')
    text=text.replace('Xtoggle events feedback RESET_N VSS VSS VDD VDD Q sky130_fd_sc_hd__dfrtp_1',
        f'Xtoggle events feedback RESET_N VSS VSS VDD VDD QT sky130_fd_sc_hd__dfrtp_{drive}\n'
        'Xoutput QT VSS VSS VDD VDD Q sky130_fd_sc_hd__buf_4')
    return text


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'clocking_v2.json',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/spice_dispatch.py']
    specs=[dict(process=p,temperature=t,mhz=f,slew_ps=s,phase_error_ps=e,buffers=b,drive=d)
        for p,t,f,s,e,b,d in itertools.product(['ss'],[40],[410],[20,250],[0,-140],[0,2],[2,4])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},pdk=str(pdk),
        pdk_sha256=base.sha(pdk),simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/digital_dcc_drive_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    text=base.cell_library(pdk); full=pdk.read_text()
    for name in ['inv_2','inv_4','buf_4','dfrtp_2','dfrtp_4']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1: raise ValueError('Missing cell '+name)
        text+='\n'+found[0]+'\n'
    base.write(out/'cells.spice',text)
    tasks=[]
    for n,spec in enumerate(specs):
        lib=f'dcc_b{spec["buffers"]}_d{spec["drive"]}.spice'
        if not (out/lib).exists():base.write(out/lib,circuit(spec['buffers'],spec['drive']))
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',base.fixture(out,spec,lib))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


# base.bound already validates an arbitrary identity's complete code set,
# simulator, native library and decks. The namespace/version check is added here.
original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcc_drive_v2'):
        raise ValueError('Require stronger-drive context')
    m=original_bound(out)
    if m['identity']['version']!=VERSION:raise ValueError('Wrong experiment version')
    return m


@contextmanager
def profile():
    previous=base.bound; base.bound=bound
    try: yield
    finally: base.bound=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound'])
    p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Require artifact')
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
