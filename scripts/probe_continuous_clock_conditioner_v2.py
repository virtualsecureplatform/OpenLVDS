#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continuous 410 MHz conditioning at the real fixed clock/monitor fanout.

Reuse the exact repaired analog front end and distributed-RC bias. The actual
buffered-TG DCC loads its input clocks while held in reset. This isolates input
conditioning bandwidth/time walk; it cannot qualify DCC startup or run timing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import numpy as np
import continuous_clock_conditioner_v2 as clean
import probe_dcc_tg_buffered_v2 as dcc
import dll_analog_frontend_v2_tailtrim as frontend
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic
from run_ngspice import read_raw

ROOT=dcc.ROOT
VERSION='native-continuous-clock-conditioning-with-held-dcc-v2.1'
RAW_START_NS=22


def fixture(out,spec,devices):
    period=1000/spec['mhz'];a=spec['slew0_ps']/1000;b=spec['slew180_ps']/1000
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    pins=dict(zip(dcc.circuit.PORTS,['0','VDD','QD','P0','P180','0']))
    probes={'R0','R180','F0','F180','P0','P180','MON0','MON180','QD','VDD','VDDIO','PB','NB','XF:VCM'}
    probes.update(n for d in devices for n in d['terminals'] if n!='0')
    return (f'OpenLVDS {VERSION}\n.lib "{model}" {spec["process"]}\n'
        f'.include "{out}/frontend.spice"\n.include "{out}/bias.spice"\n.include "{out}/clean.spice"\n.include "{out}/dcc.spice"\n'
        f'.options device temp={spec["temperature"]}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VDD VDD 0 1.8\nVDDIO VDDIO 0 3.3\nIREF PB 0 DC 35u\nXB PB NB VDDIO 0 lvds_bias\n'
        f'VR0 R0 0 PULSE(0 1.8 {RAW_START_NS}n {a:.15g}n {a:.15g}n {spec["duty"]*period-a:.15g}n {period:.15g}n)\n'
        f'VR180 R180 0 PULSE(0 1.8 {RAW_START_NS+period/2+(a-b)/2:.15g}n {b:.15g}n {b:.15g}n {spec["duty"]*period-b:.15g}n {period:.15g}n)\n'
        f'XF R0 R180 F0 F180 PB VDDIO VDD 0 {frontend.PAIR}\n'
        f'XC F0 F180 P0 P180 MON0 MON180 VDD 0 {clean.NAME}\n'
        'XD '+' '.join(pins[p] for p in dcc.circuit.PORTS)+' '+dcc.circuit.NAME+'\nCQD QD 0 20f\n'
        f'.tran 1p {RAW_START_NS+22*period:.15g}n 0 1p\n.print tran '+' '.join('V('+n+')' for n in sorted(probes))+'\n.end\n')


def crossings(t,v,threshold=.9,rising=True):
    mask=((v[:-1]<threshold)&(v[1:]>=threshold)) if rising else ((v[:-1]>threshold)&(v[1:]<=threshold))
    i=np.flatnonzero(mask);return t[i]+(threshold-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])


def measure(folder,task,devices):
    spec=task['spec'];names,w=read_raw(folder/'bench.raw');index={n:i for i,n in enumerate(names)};t=w[:,index['time']]*1e12
    period=1e6/spec['mhz'];stop=RAW_START_NS*1000+22*period;start=RAW_START_NS*1000+8*period;end=stop-2*period
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete/nonfinite continuous conditioner waveform')
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,index['v('+n.replace(':','.').lower()+')']]
    channels={};latencies={};integrity=True
    for raw,node in [('R0','P0'),('R180','P180')]:
        a=crossings(t,get(raw));b=crossings(t,get(node));lat=[];rise=[];fall=[]
        low=crossings(t,get(node),.18);high=crossings(t,get(node),1.62);down=crossings(t,get(node),rising=False)
        for x,y in zip(a,a[1:]):
            if not start<=x<end:continue
            selected=b[(b>x)&(b<y)]
            if len(selected)!=1:integrity=False;continue
            q=selected[0];lat.append(float(q-x));lo=low[(low>x)&(low<q)];hi=high[(high>q)&(high<y)]
            if len(lo)==1 and len(hi)==1:rise.append(float(hi[0]-lo[0]))
            nxt=down[down>q]
            if len(nxt):fall.append(float(nxt[0]-q))
        if len(lat)<8 or len(rise)!=len(lat):integrity=False
        latencies[node]=lat
        channels[node]=dict(samples=len(lat),rising_latency_range_ps=[min(lat),max(lat)] if lat else None,
            rise_10_90_range_ps=[min(rise),max(rise)] if rise else None,high_width_range_ps=[min(fall),max(fall)] if fall else None)
    count=min(len(latencies['P0']),len(latencies['P180']));phase=[b-a for a,b in zip(latencies['P0'][:count],latencies['P180'][:count])]
    stress=[]
    for d in devices:
        values=[get(n) for n in d['terminals']];peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],model=d['model'],max_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    vcm=get('XF:VCM')[t>=RAW_START_NS*1000];phase_max=max(map(abs,phase)) if phase else None
    common=bool(np.max(np.abs(vcm-.9))<=.01);health=all(d['passed'] for d in stress)
    return dict(clock_event_integrity_passed=bool(integrity),channels=channels,conditioned_half_spacing_error_ps=phase,
        maximum_half_spacing_error_ps=phase_max,phase_20ps_feasibility_diagnostic=bool(phase_max is not None and phase_max<=20),
        common_mode_min_v=float(vcm.min()),common_mode_max_v=float(vcm.max()),common_mode_passed=common,
        terminal_stress=stress,terminal_screen_passed=health,clock_conditioning_feasibility_passed=bool(integrity and common and health and phase_max is not None and phase_max<=20),
        dcc_held_in_reset=True,qualified_phy=False,scope='Continuous input-conditioning feasibility under native fixed clock/monitor loads only; DCC held in reset, no run/startup, five-channel, physical or PHY admission')


def prepare(parent,front):
    dm=dcc.bound(parent);fm=json.loads((front/'manifest.json').read_text());fi=fm['identity'];pdk=Path(dm['identity']['pdk'])
    if (fi['version']!='repaired-native-threshold-fifteen-pvt-v2.1' or sha(pdk)!=fi['pdk_sha256']
        or any(sha(front/n)!=h for n,h in fm['libraries'].items())):raise ValueError('Retained conditioner library binding changed')
    original,ds=frontend.circuit('tail140_w20');front_ds=[d for d in fm['tasks'][0]['devices'] if d['name'].startswith('XF:')]
    if original.replace('w=22 l=22','w=30 l=30')!=(front/'frontend.spice').read_text() or ds!=front_ds:
        raise ValueError('Retained conditioner differs from its native MOS/repair generator')
    source,_=dcc.circuit.source('tg1',pdk.read_text())
    if source!=(parent/'tg1.spice').read_text():raise ValueError('Held DCC source regeneration mismatch')
    clean_text=clean.source(pdk.read_text());mapping=dict(REF='R0',FDB='R180',REF_FAST='F0',FDB_FAST='F180',VDDD='VDD',VDDIO='VDDIO',PB='PB')
    devices=[dict(name=d['name'],model=d['model'],limit_v=5.5 if d['model']=='sky130_fd_pr__pfet_g5v0d10v5' else 1.95,
        terminals=[mapping.get(n,n) for n in d['terminals']]) for d in ds]
    devices += clean.mapped_mos((front/'bias.spice').read_text(),dict(IREF='PB',NB='NB',VDDIO='VDDIO',VSS='0'),'XB')
    devices += clean.mapped_mos(clean_text,dict(F0='F0',F180='F180',P0='P0',P180='P180',MON0='MON0',MON180='MON180',VPWR='VDD',VGND='0'),'XC')
    devices += clean.mapped_mos(source,dict(VGND='0',VPWR='VDD',clock_out='QD',phase0='P0',phase180='P180',reset_n='0'),'XD')
    paths=[Path(__file__),Path(clean.__file__),Path(dcc.__file__),Path(dcc.circuit.__file__),ROOT/'scripts/dcc_tg_combiner_v2.py',
        ROOT/'scripts/dcc_nand_latch_v2.py',ROOT/'scripts/dcc_nand_mid_shunt_v2.py',ROOT/'scripts/native_static_cells_v2.py',
        ROOT/'scripts/build_compound_drivers_v3.py',Path(frontend.__file__),ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        parent/'manifest.json',parent/'tg1.spice',front/'manifest.json',front/'frontend.spice',front/'bias.spice']
    specs=[dict(process=p,temperature=40,mhz=410,slew0_ps=a,slew180_ps=b,duty=d)
        for p,(a,b),d in itertools.product(['ss','sf'],[(100,100),(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),frontend=str(front.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=dm['identity']['pdk_files'],simulator=provenance(),specs=specs,devices=devices,
        raw_start_ns=RAW_START_NS,held_dcc='tg1',load_scope='Actual buffered DCC held in reset; permanent native buf8 monitor input and fixed native 4x4 MIM rails')
    out=ROOT/'build/diagnostics/continuous_clock_conditioner_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name,text in [('frontend.spice',(front/'frontend.spice').read_text()),('bias.spice',(front/'bias.spice').read_text()),('clean.spice',clean_text),('dcc.spice',source)]:write(out/name,text)
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices));tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):
        raise ValueError('Continuous clock conditioner changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:
            raise ValueError('Conditioner task matrix/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior continuous conditioner pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='continuous_clock_conditioner_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode();result=measure(folder,task,m['identity']['devices'])
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='continuous_conditioner_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);p.add_argument('--frontend',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':
        if a.frontend is None:p.error('Provide the exact retained repaired frontend context')
        print(prepare(out,a.frontend.resolve()),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
