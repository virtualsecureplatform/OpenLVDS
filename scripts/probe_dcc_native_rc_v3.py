#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native routed DCC load/slew/startup pilot; no whole-clock or PHY admission.

Use the unchanged checked extraction, including the PDK's special narrow NFET
subcircuit. Save every MOS terminal and measure actual 0.9 V input crossings.
No waveform translation, ideal internal timing or model substitution is used.
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
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_library import checked_netlist
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from run_ngspice import read_raw

ROOT=Path(__file__).resolve().parents[1]
VERSION='routed-dcc-load-slew-startup-pilot-v2.2'
NAME='openlvds_dcc_clock_hold_v2'
SIGNALS={'pulse0':'first_ff.Q','pulse180':'second_ff.Q','events':'combine.X',
         'feedback':'toggle_feedback.Y','clear0':'first_ff.RESET_B','clear180':'second_clear.X'}


def witnesses(parent):
    """Check retained recovery inputs without importing its PNR interpreter."""
    manifest=json.loads((parent/'manifest.json').read_text());identity=manifest['identity']
    if (identity['version']!='dcc-complete-flow-summary-recovery-v2.1'
        or parent.name!=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]):
        raise ValueError('Unexpected DCC recovery identity')
    for name,digest in {**identity['files'],**identity['code']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Changed DCC recovery witness: '+name)
    summary=json.loads((parent/'summary.json').read_text());audit=json.loads((parent/'rc_audit.json').read_text())
    info=json.loads((parent/'extraction.json').read_text());text=checked_netlist(info)
    if (not summary['physical_implementation_passed'] or not audit['passed']
        or info['netlist_sha256']!=audit['netlist_sha256']
        or info['source_scope_sha256']!=audit['reference_sha256']
        or sha(parent/'rc_audit/lvs.log')!=audit['report_sha256']
        or sha(parent/'rc_audit/reference.spice')!=audit['reference_sha256']):
        raise ValueError('DCC extraction/topology receipt mismatch')
    # Physical signoff and RC must identify precisely the same routed GDS.
    gds=ROOT/summary['run']/'final/gds'/f'{NAME}.gds'
    if sha(gds)!=info['gds_sha256']:raise ValueError('DCC GDS mismatch')
    files=[parent/n for n in ['manifest.json','summary.json','state.json','extraction.json','rc_audit.json',
                              'rc_audit/lvs.log','rc_audit/reference.spice']]
    files += [ROOT/info['netlist'],ROOT/info['raw_netlist'],gds]
    files += [ROOT/n for n in {**identity['files'],**identity['code']}]
    return info,text,files


def terminals(text):
    result=[]
    for line in text.splitlines():
        words=line.split()
        if words and words[0].lower().startswith('x') and len(words)>5:
            if words[3]=='sky130_fd_pr__res_generic_po':continue
            if not words[5].startswith('sky130_fd_pr__') or 'fet_' not in words[5]:
                raise ValueError('Unexpected extracted active device')
            result.append(words[1:5])
    if not result:raise ValueError('No native MOS devices')
    return result


def fixture(out,spec,info,text):
    period=1000/spec['mhz'];s0=spec['slew0_ps']/1000;s1=spec['slew180_ps']/1000
    # Compensate slew-dependent source crossing time. PULSE TD alone is not
    # an edge measurement; both actual rising crossings must be T/2 apart.
    td1=2+period/2+(s0-s1)/2
    release=2+3*period+s0/2+.150
    reset_start=release-.010;reset_end=release+.010
    stop=2+22*period
    pg={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}
    if set(info['ports'])!=set(pg):raise ValueError('Unexpected native DCC interface')
    probes=['P0','P180','RESET_N','Q','VDD']+['XD:'+v for v in SIGNALS.values()]
    pg_nodes={p:pg[p] for p in info['ports']}
    for node in sorted({n for device in terminals(text) for n in device}):
        target=pg_nodes.get(node,'XD:'+node)
        if target!='0' and target not in probes:probes.append(target)
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION}\n.lib "{model}" {spec["process"]}\n'
        f'.include "{out}/dcc_native.spice"\n.options device temp={spec["temperature"]}\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        f'VR RESET_N 0 PWL(0 0 {reset_start:.15g}n 0 {reset_end:.15g}n 1.8)\n'
        f'VP0 P0 0 PULSE(0 1.8 2n {s0:.15g}n {s0:.15g}n {spec["duty"]*period-s0:.15g}n {period:.15g}n)\n'
        f'VP180 P180 0 PULSE(0 1.8 {td1:.15g}n {s1:.15g}n {s1:.15g}n {spec["duty"]*period-s1:.15g}n {period:.15g}n)\n'
        'XD '+' '.join(pg[p] for p in info['ports'])+' '+NAME+'\n'
        f'CQ Q 0 {spec["load_ff"]}f\n.tran 1p {stop:.15g}n 0 1p\n'
        '.print tran '+' '.join('V('+p+')' for p in probes)+'\n.end\n')


def analyze(folder,spec,info,text):
    names,w=read_raw(folder/'bench.raw');index={n:i for i,n in enumerate(names)};t=w[:,index['time']]*1e12
    period=1e6/spec['mhz'];stop=2000+22*period
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete/nonfinite native DCC transient')
    def get(node):return w[:,index['v('+node.replace(':','.').lower()+')']]
    def edges(node,up=True):return crossings(t,get(node),up)
    e0=edges('P0');e180=edges('P180');release=edges('RESET_N')
    if len(release)!=1:raise ValueError('Reset release count')
    release=float(release[0]);first=e180[e180>release][0]
    qrise=edges('Q');qfall=edges('Q',False);qall=np.sort(np.concatenate([qrise,qfall]))
    event=edges('XD:'+SIGNALS['events'])
    source=sorted([(float(a),'P0') for a in e0 if a>release]+[(float(a),'P180') for a in e180 if a>release])
    checks=[];latencies=[]
    for (a,phase),(b,_) in zip(source,source[1:]):
        ev=event[(event>a)&(event<b)];q=qall[(qall>a)&(qall<b)]
        # Native output_drive inverts the reset-low toggle FF. Delivered Q
        # starts HIGH, falls on the first P180 event and rises on PH0.
        correct=qrise if phase=='P0' else qfall
        directional=correct[(correct>a)&(correct<b)]
        checks.append(len(ev)==1 and len(q)==1 and len(directional)==1)
        if len(q)==1:latencies.append(float(q[0]-a))
    startup=bool(len(qall[qall<first])==0 and source[0][1]=='P180')
    start=2000+8*period;end=stop-period
    window=lambda a:a[(a>=start)&(a<end)]
    high=[];low=[]
    for rising,falling,durations in [(qrise,qfall,high),(qfall,qrise,low)]:
        for a in window(rising):
            following=falling[falling>a]
            if len(following):durations.append(float(following[0]-a))
    half=max(abs(np.mean(high)-period/2),abs(np.mean(low)-period/2)) if high and low else None
    # Measure all six pairwise MOS terminal voltages, not just public rails.
    pg={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}
    zeros=np.zeros(len(t));peak=0.;worst=None
    for number,device in enumerate(terminals(text)):
        values=[zeros if n=='VGND' else get(pg.get(n,'XD:'+n)) for n in device]
        for a,b in itertools.combinations(range(4),2):
            value=float(np.max(np.abs(values[a]-values[b])))
            if value>peak:peak=value;worst=dict(device=number,terminal_pair=[a,b],nodes=[device[a],device[b]])
    spacing=float(np.max(np.abs(np.diff([a for a,_ in source])-period/2)))
    return dict(event_integrity_passed=bool(checks and all(checks)),checked_events=len(checks),
        startup_no_early_toggle_passed=startup,actual_source_half_spacing_error_ps=spacing,
        output_latency_range_ps=[min(latencies),max(latencies)] if latencies else None,
        mean_half_cycle_error_ps=float(half) if half is not None else None,
        half_cycle_passed=bool(half is not None and half<=50),
        output_rising_phase='P0',phase0_delivery_passed=bool(checks and all(checks) and startup),
        terminal_abs_peak_v=peak,terminal_peak_location=worst,terminal_screen_passed=peak<=1.95,
        observed_voltage_range_v=[float(np.min(w[:,1:])),float(np.max(w[:,1:]))],
        qualified_phy=False,scope='Native routed DCC pilot only; exact output inversion and release polarity checked; no delivered clock admission')


def prepare(parent):
    info,text,files=witnesses(parent)
    code=[Path(__file__),ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/spice_library.py',
          ROOT/'scripts/run_ngspice.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    # Native corner files explicitly implement special_nfet_01v8 using valid
    # regular NFET bins. Bind that evidence and use the unmodified PDK .lib.
    models=[pdk/'libs.tech/ngspice/sky130.lib.spice',pdk/'libs.tech/magic/sky130A.tech']
    models += sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    specs=[dict(process=p,temperature=40,mhz=410,load_ff=load,slew0_ps=s0,slew180_ps=s1,duty=duty)
        for p,load,(s0,s1),duty in itertools.product(['ss','sf'],[20,100,200],[(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files={str(p):sha(p) for p in models},simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_native_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'dcc_native.spice',text);tasks=[]
    for i,spec in enumerate(specs):
        folder=out/str(i);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,info,text))
        tasks.append(dict(id=str(i),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,extraction=info,library_sha256=sha(out/'dcc_native.spice'),qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'dcc_native.spice')!=m['library_sha256']
        or any(sha(out/task['id']/'bench.cir')!=task['deck_sha256'] for task in m['tasks'])):
        raise ValueError('Native DCC pilot binding changed')
    checked_netlist(m['extraction']);return m


def run(out):
    m=bound(out);text=(out/'dcc_native.spice').read_text()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native DCC pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_native_rc_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode()
                result=analyze(folder,task['spec'],m['extraction'],text)
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='native_rc_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
