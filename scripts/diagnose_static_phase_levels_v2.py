#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Separate phase event order from clock-level margin using completed native cases.

Individual completed cases can diagnose an unfinished campaign. They cannot
admit its remaining matrix, actual DCC first events, hardware warmup or PHY.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import probe_static_phase_clock_release_v6 as pilot
import probe_static_phase_clock_release_v5 as baseline
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import crossings

ROOT=pilot.ROOT
VERSION='native-static-phase-order-versus-clock-level-diagnosis-v2.1'
CONTEXT='static_phase_level_diagnosis_v2'
NODES={'low0':'XD:XR:low0','high1':'XD:XR:high1','low1':'XD:XR:low1',
       'prepare':'PREPARE','armed':'XD:XR:armed','release':'RESET_N'}


def measure(folder,producer,m,task):
    r=json.loads((folder/'summary.json').read_text());spec=task['spec'];mos=m['identity']['devices'][spec['variant']]
    if r['task']!=task or r['error'] is not None or r['result'] is None:raise ValueError('Require a complete numerical native case')
    if (folder/'bench.cir').read_text()!=producer.fixture(folder.parent,spec,mos):raise ValueError('Native case fixture changed')
    if not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files']):raise ValueError('Missing native case outputs')
    for n,h in r['files'].items():
        if pilot.sha(folder/n)!=h:raise ValueError('Changed completed native case witness')
    if producer.measure(folder,spec,mos)!=r['result']:raise ValueError('Native case independent remeasurement changed')
    required={'v(clk)',*['v('+n.replace(':','.').lower()+')' for n in NODES.values()]}
    names,w=validate(folder/'bench.raw',required,26e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    clk=w[:,idx['v(clk)']];rise=crossings(t,clk);fall=crossings(t,clk,False)
    # Shift the analysis threshold only, retaining the original simulated data.
    low_exit=crossings(t,clk+.72);signals={};events={}
    for name,node in NODES.items():
        times=crossings(t,w[:,idx['v('+node.replace(':','.').lower()+')']]);events[name]=times
        if len(times)<1:raise ValueError('Missing required phase transition')
        event=times[0];value=float(np.interp(event,t,clk))
        details=dict(first_event_ps=float(event),all_rising_events_ps=times.tolist(),clock_at_first_event_v=value,
                     clock_near_event_v={str(dt):float(np.interp(event+dt,t,clk)) for dt in [-200,-100,-50,0,50,100,200]})
        if name in ['low0','low1','armed']:
            preceding=fall[fall<event];following=rise[rise>event]
            if len(preceding)==0 or len(following)==0:raise ValueError('Unbounded low-phase interval')
            exits=low_exit[(low_exit>preceding[-1])&(low_exit<following[0])]
            if len(exits)==0:raise ValueError('Missing clock low-limit exit')
            details.update(low_level_limit_v=.18,low_level_passed=value<.18,
                           first_low_limit_exit_margin_ps=float(exits[0]-event),
                           next_clock_midpoint_margin_ps=float(following[0]-event))
        signals[name]=details
    if len(rise)<4:raise ValueError('Missing qualified clock epochs')
    order=bool(events['low0'][0]<rise[1]<events['high1'][0]<events['low1'][0]<rise[2]<events['prepare'][0])
    arm_order=bool(events['prepare'][0]<events['armed'][0]<rise[3]<events['release'][0])
    result=dict(case=task['id'],spec=spec,clock_rise_ps=rise.tolist(),clock_fall_ps=fall.tolist(),states=signals,
        intermediate_event_order_passed=order,arming_event_order_passed=arm_order,
        low_clock_level_failures=[n for n in ['low0','low1','armed'] if not signals[n]['low_level_passed']],
        terminal_peak_v=max(d['max_terminal_difference_v'] for d in r['result']['terminal_stress']),
        original_counter_feasibility_passed=r['result']['counter_feasibility_passed'],qualified_phy=False)
    return result,[folder/'summary.json',*[folder/n for n in r['files']]]


def diagnose(parent,case):
    m=pilot.bound(parent);profile=ROOT/m['identity']['baseline_profile'];pilot.selected_profile(profile)
    pr=json.loads((profile/'summary.json').read_text());bp=ROOT/pr['identity']['parent'];bm=baseline.bound(bp)
    task=next(t for t in m['tasks'] if t['id']==case);wanted=dict(task['spec'],variant='o1')
    matches=[r for r in pr['rows'] if r['task']['spec']==wanted]
    if len(matches)!=1:raise ValueError('Require exact independently verified matching baseline case')
    bt=matches[0]['task']
    if bt not in bm['tasks']:raise ValueError('Baseline task changed')
    old,files=measure(bp/bt['id'],baseline,bm,bt)
    new,paths=measure(parent/case,pilot,m,task);files+=paths
    if not old['original_counter_feasibility_passed']:raise ValueError('Require the retained passing component baseline')
    files += [parent/'manifest.json',bp/'manifest.json',profile/'summary.json',Path(__file__),Path(pilot.__file__),Path(baseline.__file__),
              ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case=case,baseline=str(bp.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    result=dict(identity=identity,baseline=old,current=new,
        isolated_clock_level_failure=bool(new['intermediate_event_order_passed'] and new['arming_event_order_passed'] and new['low_clock_level_failures']),
        qualified_phy=False,electrical_qualification_passed=False,
        scope='Two fully remeasured matching native cases; diagnostic separation of event order and clock-low voltage at state assertions, not whole-campaign, DCC first-event, hardware-warmup, full-PVT or PHY admission')
    if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Native diagnostic witnesses changed')
    out.mkdir(parents=True,exist_ok=False);pilot.atomic(out/'summary.json',result);return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--case',choices=['0','1','2','3'],required=True)
    a=p.parse_args();print(diagnose(a.artifact.resolve(),a.case),flush=True)
