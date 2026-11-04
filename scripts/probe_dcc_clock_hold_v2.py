#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Repair SF repeated pulse generation with a clock-aware local reset latch.

Keep all failed source bytes. This bounded SF40/SS40 410 MHz pilot tests two
reset-logic drives, 20/250 ps input slew and 0/+/-140 ps event spacing error.
It retains actual 30/70% input duty and the unchanged 50 ps half-cycle limit.
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
import expand_digital_dcc_v2 as failed

ROOT=base.ROOT
VERSION='dcc-clock-aware-local-reset-v2.1'


def circuit(drive):
    if drive not in (1,2):raise ValueError('Undeclared reset logic drive')
    lines=['.subckt dcc_source P0 P180 RESET_N Q VDD VSS',
           'XTIE VSS VSS VDD VDD HI LO sky130_fd_sc_hd__conb_1']
    for prefix,clock in [('a','P0'),('b','P180')]:
        lines += [f'X{prefix}ff {clock} HI {prefix}reset VSS VSS VDD VDD {prefix} sky130_fd_sc_hd__dfrtp_1',
            f'X{prefix}clk {clock} VSS VSS VDD VDD {prefix}clk_n sky130_fd_sc_hd__inv_1',
            f'X{prefix}q {prefix} VSS VSS VDD VDD q{prefix}_n sky130_fd_sc_hd__inv_1',
            f'X{prefix}hold q{prefix}_n {prefix}reset {prefix}clk_n VSS VSS VDD VDD {prefix}clear_n sky130_fd_sc_hd__a21oi_{drive}',
            f'X{prefix}clear {prefix}clear_n RESET_N VSS VSS VDD VDD {prefix}reset sky130_fd_sc_hd__and2b_{drive}']
    lines += ['Xor a b VSS VSS VDD VDD events sky130_fd_sc_hd__or2_1',
        'Xinv QT VSS VSS VDD VDD feedback sky130_fd_sc_hd__inv_1',
        'Xtoggle events feedback RESET_N VSS VSS VDD VDD QT sky130_fd_sc_hd__dfrtp_1',
        'Xoutput QT VSS VSS VDD VDD Q sky130_fd_sc_hd__inv_4','.ends dcc_source']
    return '\n'.join(lines)+'\n'


def fixture(out,spec):
    text=base.fixture(out,spec,f'hold{spec["reset_drive"]}.spice')
    return text.replace('V(XD:feedback)','V(XD:QT) V(XD:aclk_n) V(XD:bclk_n) V(XD:feedback)')


original_measure=base.measure

def measure(folder,spec):
    result=original_measure(folder,spec)
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    get=lambda n:w[:,names.index('v('+n+')')]
    checks=[]
    for p,clock in [('a','p0'),('b','p180')]:
        edges=base.crossings(t,get(clock));fall=base.crossings(t,get(clock),False)
        pulses=base.crossings(t,get('xd.'+p));ends=base.crossings(t,get('xd.'+p),False)
        for i,edge in enumerate(edges[:-1]):
            if not 10000<=edge<40000:continue
            events=pulses[(pulses>edge)&(pulses<edges[i+1])]
            count=len(events)==1;held=False
            if count:
                ending=ends[ends>events[0]];falling=fall[fall>edge]
                if len(ending) and len(falling):
                    mask=(t>ending[0]+20)&(t<falling[0]-20)
                    held=not np.any(mask) or float(np.max(get('xd.'+p+'reset')[mask]))<=.18
            checks.append(dict(channel=p,source_edge_ps=float(edge),pulse_count=len(events),held_until_fall=bool(held),passed=bool(count and held)))
    return dict(result,pulse_generator_checks=checks,pulse_generator_integrity_passed=bool(checks and all(q['passed'] for q in checks)),
        scope='Clock-aware reset source pilot only; no all-PVT, recovery/removal, physical RC or PHY admission')


def prepare(parent):
    pm=failed.bound(parent);report=json.loads((parent/'summary.json').read_text())
    sf=[r for r in report['rows'] if r['task']['spec']['process']=='sf']
    if len(sf)!=54 or any(r['error'] is not None for r in sf) or all(r['result']['event_integrity_passed'] for r in sf):
        raise ValueError('Require the complete failed SF source expansion')
    pdk=Path(pm['identity']['pdk']);model=Path(pm['identity']['model_library']) if 'model_library' in pm['identity'] else Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    files=[Path(__file__),ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',
        ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(process=p,temperature=40,mhz=410,slew_ps=s,phase_error_ps=e,buffers=0,drive=1,output_cell='inv_4',reset_drive=d)
        for d,p,s,e in itertools.product([1,2],['sf','ss'],[20,250],[0,-140,140])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):base.sha(p) for p in [parent/'manifest.json',parent/'summary.json',parent/'state.json']},
        pdk=str(pdk),pdk_sha256=base.sha(pdk),model_library=str(model),model_library_sha256=base.sha(model),simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_clock_hold_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();cells=''
    for name in ['conb_1','dfrtp_1','inv_1','inv_4','or2_1','a21oi_1','a21oi_2','and2b_1','and2b_2']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+name)
        cells+=found[0]+'\n'
    base.write(out/'cells.spice',cells)
    for d in [1,2]:base.write(out/f'hold{d}.spice',circuit(d))
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcc_clock_hold_v2'):raise ValueError('Wrong clock-hold context')
    m=original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['inputs'].items())):raise ValueError('Clock-hold context changed')
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
