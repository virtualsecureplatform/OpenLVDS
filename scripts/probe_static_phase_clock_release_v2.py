#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test a six-state alternating phase counter made only of native RC macros.

Real RC clock/REQUEST buffers, alternating sticky NAND storage and all three
DCC reset-input loads are connected. Inter-component wires remain ideal. No
actual DCC first event, full-PVT, whole-controller RC or PHY admission follows.
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
import sys
import numpy as np
import static_phase_clock_release_v2 as circuit
import phase_release_rc_families_v2 as families
import probe_guarded_phase_clock_release_v2 as previous
import probe_native_clock_components_v7 as components
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=components.ROOT
VERSION='all-native-static-alternating-phase-release-pilot-v2.1'
HARNESS='openlvds_static_phase_release_loaded_v2'
HPORTS=['RCLK','REQUEST','PREPARE','RESET_N','CLK','VPWR','VGND']


def specifications():
    return [dict(drive=drive,process='ss',temperature=40,mhz=410,duty=d,stop_level=level,input_slew_ps=100)
            for drive,d,level in itertools.product([4,8],[.4,.6],[0,1])]


def harness(rc):
    c=circuit.components;rows=['.subckt '+HARNESS+' '+' '.join(HPORTS)]
    rows.append(c.instance('clock_driver',c.CLOCK_BUFFER,dict(A='RCLK',X='CLK',VPWR='VPWR',VGND='VGND'),rc))
    rows.append('XR CLK REQUEST PREPARE RESET_N VPWR VGND '+circuit.NAME)
    for n in range(2):
        rows.append(c.instance('prepare_load'+str(n),c.MODELS['nand2_4'],
            dict(A='RESET_N',B='VPWR',Y='prepare_load'+str(n),VPWR='VPWR',VGND='VGND'),rc))
    rows.append(c.instance('mask_load',c.MODELS['nand2_8'],dict(A='RESET_N',B='VPWR',Y='mask_load',VPWR='VPWR',VGND='VGND'),rc))
    rows.append('Cmask_load mask_load VGND 20f')
    return '\n'.join(rows+['.ends '+HARNESS,''])


def fixture(out,spec,mos):
    period=1000/spec['mhz'];slew=spec['input_slew_ps']/1000;points=['0 0']
    for cycle in range(7):
        t=2+cycle*period;points += [f'{t:.15g}n 0',f'{t+slew:.15g}n 1.8']
        if cycle<6 or spec['stop_level']==0:
            end=t+spec['duty']*period;points += [f'{end:.15g}n 1.8',f'{end+slew:.15g}n 0']
    probes={'RCLK','CLK','REQUEST','PREPARE','RESET_N','VDD','XD:XR:armed','XD:XR:request_i','XD:XR:low0','XD:XR:high1','XD:XR:low1'}
    probes.update(n for d in mos for n in d['terminals'] if n!='0')
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION}\n.lib "{model}" {spec["process"]}\n.include "{out}/cells.spice"\n'
        f'.include "{out}/drive{spec["drive"]}.spice"\n.options device temp={spec["temperature"]}\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        'VRCLK RCLK 0 PWL('+' '.join(points)+')\n'
        'VREQUEST REQUEST 0 PWL(0 0 3.39n 0 3.41n 1.8 20.99n 1.8 21.01n 0 22.99n 0 23.01n 1.8)\n'
        'XD RCLK REQUEST PREPARE RESET_N CLK VDD 0 '+HARNESS+'\n.tran 1p 26n 0 1p\n'
        '.print tran '+' '.join('V('+n+')' for n in sorted(probes))+'\n.end\n')


def measure(folder,spec,mos):
    result=previous.measure(folder,spec,mos)
    names,w=validate(folder/'bench.raw',{'v(request)','v(xd.xr.request_i)'},26e-9)
    idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    external=crossings(t,w[:,idx['v(request)']]);internal=crossings(t,w[:,idx['v(xd.xr.request_i)']])
    falling=crossings(t,w[:,idx['v(xd.xr.request_i)']],False)
    if len(internal)!=2 or len(falling)!=1:raise ValueError('Buffered REQUEST event count')
    delays=internal-external
    if np.any(delays<=0):raise ValueError('Noncausal buffered REQUEST')
    extra=['low0','high1','low1']
    names,w=validate(folder/'bench.raw',{'v(xd.xr.'+n+')' for n in extra},26e-9)
    idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    def get(n):return w[:,idx['v('+n.replace(':','.').lower()+')']]
    events={n:crossings(t,get('XD:XR:'+n)) for n in extra}
    if len(events['high1'])!=1 or len(events['low1'])!=1 or len(events['low0'])!=1+(spec['stop_level']==0):
        raise ValueError('Alternating phase-state event count')
    clk=crossings(t,get('CLK'));ready=crossings(t,get('PREPARE'))
    ordered=bool(events['low0'][0]<clk[1]<events['high1'][0]<events['low1'][0]<clk[2]<ready[0])
    low_levels=all(float(np.interp(events[n][0],t,get('CLK')))<.18 for n in ['low0','low1'])
    stopped_clear=all(np.max(np.abs(get('XD:XR:'+n)[t>=24000]))<=.18 for n in ['high1','low1'])
    result.update(buffered_request_rise_delays_ps=[float(v) for v in delays],
                  intermediate_phase_events_ps={n:[float(v) for v in edges] for n,edges in events.items()},
                  alternating_phase_order_passed=ordered and low_levels,
                  stopped_clock_intermediate_clear_passed=bool(stopped_clear),
                  counter_feasibility_passed=bool(result['counter_feasibility_passed'] and ordered and low_levels and stopped_clear),
                  scope='All-native component-RC alternating sticky phase counter with buffered REQUEST and full DCC reset-input loads; no source FF or private FF guards, actual DCC first event, whole-controller RC, full-PVT or PHY admission')
    return result


def prepare(nands,clock,compound):
    if engine()!='ngspice':raise ValueError('Explicitly select pinned ngspice')
    rc={};paths=[]
    for parent in [nands,clock,compound]:
        group,files=families.witnesses(parent)
        if set(group)&set(rc):raise ValueError('Duplicate native RC model')
        rc.update(group);paths+=files
    cells='\n'.join(rc[n]['text'].rstrip() for n in sorted(rc))+'\n';variants={};ds={}
    for drive in [4,8]:
        text=circuit.source(rc,drive)+harness(rc);variants[drive]=text
        ds[str(drive)]=circuit.components.mapped_mos(cells+text,HARNESS,
            dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
    code=[Path(__file__),Path(circuit.__file__),Path(families.__file__),Path(families.compound.__file__),Path(previous.__file__),
        ROOT/'scripts/probe_guarded_clock_prepare_v3.py',
        ROOT/'scripts/native_clock_components_v3.py',ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/probe_native_clock_components_v7.py',
        ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/spice_library.py',ROOT/'scripts/reduce_rc.py',
        ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_slots.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'build/tools/ngspice.json',ROOT/'clocking_v2.json',ROOT/'clocking_duty_v2_2.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';models=[pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,families=[str(n.relative_to(ROOT)) for n in [nands,clock,compound]],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},pdk_files={str(p):sha(p) for p in models},
        simulator=provenance(),specs=specifications(),devices=ds)
    out=ROOT/'build/diagnostics/static_phase_clock_release_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells)
    for drive,text in variants.items():write(out/f'drive{drive}.spice',text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,ds[str(spec['drive'])]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/static_phase_clock_release_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):raise ValueError('Static-phase pilot changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Static-phase task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior static-phase campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='static_phase_release_v2_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'][str(task['spec']['drive'])])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='static_phase_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?')
    p.add_argument('--nands',type=Path);p.add_argument('--clock-cells',type=Path);p.add_argument('--compound',type=Path);a=p.parse_args();out=a.artifact.resolve() if a.artifact else None
    if a.action=='prepare':
        if a.nands is None or a.clock_cells is None or a.compound is None:p.error('Provide three certified native RC families')
        print(prepare(a.nands.resolve(),a.clock_cells.resolve(),a.compound.resolve()),flush=True)
    else:
        if out is None:p.error('Provide the prepared campaign')
        run(out)
