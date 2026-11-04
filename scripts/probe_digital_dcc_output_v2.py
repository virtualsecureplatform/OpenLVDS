#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate toggle CQ and output-cell polarity without changing earlier screens."""
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
VERSION='source-digital-dcc-output-polarity-v2.1'


def circuit(drive, output_cell):
    if drive not in (1,2) or output_cell not in ('inv_1','inv_2','inv_4','buf_1'):
        raise ValueError('Undeclared topology')
    text=base.circuit(0)
    text=text.replace('Xinv Q VSS VSS VDD VDD feedback', 'Xinv QT VSS VSS VDD VDD feedback')
    port='Y' if output_cell.startswith('inv') else 'X'
    text=text.replace('Xtoggle events feedback RESET_N VSS VSS VDD VDD Q sky130_fd_sc_hd__dfrtp_1',
        f'Xtoggle events feedback RESET_N VSS VSS VDD VDD QT sky130_fd_sc_hd__dfrtp_{drive}\n'
        f'Xoutput QT VSS VSS VDD VDD Q sky130_fd_sc_hd__{output_cell}')
    return text


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'clocking_v2.json',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/spice_dispatch.py']
    specs=[dict(process='ss',temperature=40,mhz=410,slew_ps=250,phase_error_ps=0,buffers=0,drive=d,output_cell=c)
        for d,c in itertools.product([1,2],['inv_1','inv_2','inv_4','buf_1'])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},pdk=str(pdk),
        pdk_sha256=base.sha(pdk),simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/digital_dcc_output_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    text=base.cell_library(pdk);full=pdk.read_text()
    for name in ['inv_2','inv_4','dfrtp_2']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing cell '+name)
        text+='\n'+found[0]+'\n'
    base.write(out/'cells.spice',text);tasks=[]
    for n,spec in enumerate(specs):
        lib=f'dcc_d{spec["drive"]}_{spec["output_cell"]}.spice'
        base.write(out/lib,circuit(spec['drive'],spec['output_cell']))
        folder=out/str(n);folder.mkdir()
        deck=base.fixture(out,spec,lib).replace('V(XD:feedback)', 'V(XD:QT) V(XD:feedback)')
        base.write(folder/'bench.cir',deck)
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcc_output_v2'):
        raise ValueError('Require output-cell context')
    m=original_bound(out)
    if m['identity']['version']!=VERSION:raise ValueError('Wrong experiment version')
    return m

@contextmanager
def profile():
    previous=base.bound;base.bound=bound
    try:yield
    finally:base.bound=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound'])
    p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Require artifact')
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
