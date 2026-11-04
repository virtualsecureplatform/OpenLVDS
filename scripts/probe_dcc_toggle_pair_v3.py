#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate routed one-shot failures and test a two-toggle/XNOR DCC alternative.

The control removes only distributed R/C from the exact routed transistor
network. Candidates use two independent 400 MHz toggle FFs and an XNOR; no
800 MHz one-shot OR or self-reset pulse loop remains. Source pilots cannot
qualify their physical implementation or select a production clock backend.
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
import probe_dcc_native_rc_v3 as native
from build_compound_drivers_v3 import cell_definition
from audit_rc import collapse
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from run_ngspice import read_raw

ROOT=native.ROOT
VERSION='reset-qualified-feedback-two-toggle-dcc-source-pilot-v2.2'


def source_pair(drive,library):
    if drive not in [1,2]:raise ValueError('Undeclared toggle drive')
    models=['dfrtp_'+str(drive),'and2b_1','xnor2_4'];definitions={}
    for short in models:
        name='sky130_fd_sc_hd__'+short;block=cell_definition(library,name)
        definitions[name]=(block.splitlines()[0].split()[2:],block.splitlines()[1:-1])
    gates=[]
    for tag,phase in [('a','phase0'),('b','phase180')]:
        gates += [(tag+'ff',models[0],dict(CLK=phase,D=tag+'n',RESET_B='reset_n',Q=tag)),
                  (tag+'feedback','and2b_1',dict(A_N=tag,B='reset_n',X=tag+'n'))]
    gates += [('combine','xnor2_4',dict(A='a',B='b',Y='clock_out'))]
    lines=['.subckt '+native.NAME+' VGND VPWR clock_out phase0 phase180 reset_n']
    # Inline native cell transistors without changing dimensions/parameters;
    # prefix private nodes so every real terminal can be saved and screened.
    for tag,short,pins in gates:
        name='sky130_fd_sc_hd__'+short;ports,body=definitions[name]
        pins=dict(VGND='VGND',VNB='VGND',VPWR='VPWR',VPB='VPWR',**pins)
        if set(pins)!=set(ports):raise ValueError('Native toggle cell interface changed')
        for line in body:
            words=line.split()
            if not words or words[0].startswith('*'):continue
            if not words[0].startswith('X') or len(words)<6 or not words[5].startswith('sky130_fd_pr__'):
                raise ValueError('Unexpected native cell transistor')
            nodes=[pins.get(n,tag+'__'+n) for n in words[1:5]]
            lines += ['X'+tag+'__'+words[0]+' '+' '.join([*nodes,*words[5:]])]
    return '\n'.join(lines+['.ends '+native.NAME,''])


def fixture(out,spec,info,text):
    deck=native.fixture(out,spec,info,text).replace(str(out/'dcc_native.spice'),str(out/(spec['variant']+'.spice')))
    pg={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}
    probes=['P0','P180','RESET_N','Q','VDD']
    for n in sorted({n for dev in native.terminals(text) for n in dev}):
        node=pg.get(n,'XD:'+n)
        if node!='0' and node not in probes:probes.append(node)
    return re.sub(r'(?m)^\.print tran .*$',lambda _:'.print tran '+' '.join('V('+p+')' for p in probes),deck)


def measure(folder,spec,info,text):
    names,w=read_raw(folder/'bench.raw');idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    period=1e6/spec['mhz'];stop=2000+22*period
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete/nonfinite DCC alternative transient')
    def get(n):return w[:,idx['v('+n.replace(':','.').lower()+')']]
    def edges(n,up=True):return crossings(t,get(n),up)
    release=edges('RESET_N')
    if len(release)!=1:raise ValueError('Reset release count')
    e0,e1=edges('P0'),edges('P180');qr,qf=edges('Q'),edges('Q',False)
    output=np.sort(np.r_[qr,qf]);source=sorted([(float(e),'P0') for e in e0 if e>release[0]]+[(float(e),'P180') for e in e1 if e>release[0]])
    checks=[];latency=[]
    for (a,phase),(b,_) in zip(source,source[1:]):
        all_edges=output[(output>a)&(output<b)];direction=qr if phase=='P0' else qf
        valid=direction[(direction>a)&(direction<b)]
        checks.append(dict(source_edge_ps=a,phase=phase,output_count=len(all_edges),direction_count=len(valid),passed=len(all_edges)==1 and len(valid)==1))
        if len(all_edges)==1:latency.append(float(all_edges[0]-a))
    startup=bool(source and source[0][1]=='P180' and not np.any(output<source[0][0]))
    durations=[]
    for first,second in [(qr,qf),(qf,qr)]:
        widths=[]
        for a in first[(first>=2000+8*period)&(first<stop-period)]:
            following=second[second>a]
            if len(following):widths.append(float(following[0]-a))
        durations.append(widths)
    half=max(abs(float(np.mean(d))-period/2) for d in durations) if all(durations) else None
    pg={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}
    zeros=np.zeros(len(t));peak=0.;worst=None
    for i,device in enumerate(native.terminals(text)):
        values=[zeros if n=='VGND' else get(pg.get(n,'XD:'+n)) for n in device]
        for a,b in itertools.combinations(range(4),2):
            value=float(np.max(np.abs(values[a]-values[b])))
            if value>peak:peak=value;worst=dict(device=i,nodes=[device[a],device[b]])
    passed=bool(checks and all(c['passed'] for c in checks) and startup and half is not None and half<=50 and peak<=1.95)
    return dict(output_event_checks=checks,event_integrity_passed=bool(checks and all(c['passed'] for c in checks)),
        startup_passed=startup,half_cycle_error_ps=half,half_cycle_passed=bool(half is not None and half<=50),
        half_cycle_width_ranges_ps=[[min(d),max(d)] if d else None for d in durations],
        maximum_individual_half_cycle_error_ps=max(abs(v-period/2) for d in durations for v in d) if all(durations) else None,
        output_latency_range_ps=[min(latency),max(latency)] if latency else None,terminal_abs_peak_v=peak,
        terminal_peak_location=worst,terminal_screen_passed=peak<=1.95,pilot_passed=passed,
        qualified_phy=False,scope='Unrouted two-toggle source alternative or wire-collapsed routed control only; no native RC timing admission')


def prepare(parent,failed):
    m=native.bound(parent);recovery=ROOT/m['identity']['parent'];info,text,_=native.witnesses(recovery)
    import probe_dcc_toggle_pair_v2 as original
    original.bound(failed)
    for k in ['8','9']:
        row=json.loads((failed/k/'summary.json').read_text())
        if row['error'] is not None or row['task']['spec']['variant']!='pair1' or row['result']['startup_passed']:
            raise ValueError('Require retained native source startup failures')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    variants={'gated1':source_pair(1,pdk.read_text()),'gated2':source_pair(2,pdk.read_text())}
    files=[Path(__file__),Path(native.__file__),ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/audit_rc.py',
           ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',
           parent/'manifest.json',Path(original.__file__),failed/'manifest.json',failed/'8/summary.json',failed/'9/summary.json']
    specs=[dict(variant=v,process=p,temperature=40,mhz=410,load_ff=20,slew0_ps=s0,slew180_ps=s1,duty=d)
        for v,p,(s0,s1),d in itertools.product(variants,['ss','sf'],[(100,100),(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=sha(pdk),pdk_files=m['identity']['pdk_files'],simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_toggle_pair_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    for n,body in variants.items():write(out/(n+'.spice'),body)
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,info,variants[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,extraction_interface=info,
        libraries={n:sha(out/n) for n in [v+'.spice' for v in variants]},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or sha(Path(i['pdk']))!=i['pdk_sha256']
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or provenance()!=i['simulator']
        or any(sha(out/n)!=h for n,h in m['libraries'].items())
        or any(sha(out/task['id']/'bench.cir')!=task['deck_sha256'] for task in m['tasks'])):
        raise ValueError('DCC alternative pilot changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior DCC alternative pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_toggle_pair_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode()
                result=measure(folder,task['spec'],m['extraction_interface'],(out/(task['spec']['variant']+'.spice')).read_text())
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='source_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    p.add_argument('--failed-pair',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':
        if a.failed_pair is None:p.error('Provide retained startup failure artifact')
        print(prepare(out,a.failed_pair.resolve()),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
