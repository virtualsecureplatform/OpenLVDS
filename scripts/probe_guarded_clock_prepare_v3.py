#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate guarded three-FF prepare/release timing and stopped-clock clearing.

Real RC clock/output buffers and two data-input/one mask-input NAND loads are
connected. Guarded FFs are native source plus actual MIM devices, not extracted
custom cells. No DCC event, full-PVT, physical-clock or PHY admission follows.
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
import guarded_clock_prepare_v2 as circuit
import diagnose_native_ff_reset_guards_v2 as diagnosis
import probe_native_clock_components_v7 as components
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=components.ROOT
VERSION='guarded-three-ff-reset-extended-prepare-release-pilot-v2.2'
HARNESS='openlvds_clock_prepare_loaded_v2'
HPORTS=['RCLK','REQUEST','PREPARE','RESET_N','CLK','VPWR','VGND']


def specifications():
    return [dict(guard_um=size,process='ss',temperature=40,mhz=410,duty=d,stop_level=level,input_slew_ps=100)
            for size,d,level in itertools.product([1,2],[.4,.6],[0,1])]


def harness(rc):
    c=circuit.components;rows=['.subckt '+HARNESS+' '+' '.join(HPORTS)]
    rows.append(c.instance('clock_driver',c.CLOCK_BUFFER,dict(A='RCLK',X='CLK',VPWR='VPWR',VGND='VGND'),rc))
    rows.append('XR CLK REQUEST PREPARE RESET_N VPWR VGND '+circuit.NAME)
    for n in range(2):
        rows.append(c.instance('prepare_load'+str(n),c.MODELS['nand2_4'],
            dict(A='PREPARE',B='VPWR',Y='prepare_load'+str(n),VPWR='VPWR',VGND='VGND'),rc))
    rows.append(c.instance('mask_load',c.MODELS['nand2_8'],dict(A='RESET_N',B='VPWR',Y='mask_load',VPWR='VPWR',VGND='VGND'),rc))
    rows.append('Cmask_load mask_load VGND 20f')
    return '\n'.join(rows+['.ends '+HARNESS,''])


def fixture(out,spec,mos):
    period=1000/spec['mhz'];slew=spec['input_slew_ps']/1000;points=['0 0']
    for cycle in range(7):
        t=2+cycle*period;points += [f'{t:.15g}n 0',f'{t+slew:.15g}n 1.8']
        if cycle<6 or spec['stop_level']==0:
            end=t+spec['duty']*period;points += [f'{end:.15g}n 1.8',f'{end+slew:.15g}n 0']
    probes={'RCLK','CLK','REQUEST','PREPARE','RESET_N','VDD'}
    probes.update(n for d in mos for n in d['terminals'] if n!='0')
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION}\n.lib "{model}" {spec["process"]}\n.include "{out}/cells.spice"\n'
        f'.include "{out}/guard{spec["guard_um"]}.spice"\n.options device temp={spec["temperature"]}\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        'VRCLK RCLK 0 PWL('+' '.join(points)+')\n'
        'VREQUEST REQUEST 0 PWL(0 0 3.39n 0 3.41n 1.8 20.99n 1.8 21.01n 0 22.99n 0 23.01n 1.8)\n'
        'XD RCLK REQUEST PREPARE RESET_N CLK VDD 0 '+HARNESS+'\n.tran 1p 26n 0 1p\n'
        '.print tran '+' '.join('V('+n+')' for n in sorted(probes))+'\n.end\n')


def measure(folder,spec,mos):
    requested={'v(clk)','v(request)','v(prepare)','v(reset_n)',*[('v('+n.replace(':','.').lower()+')') for d in mos for n in d['terminals'] if n!='0']}
    names,w=validate(folder/'bench.raw',requested,26e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
    def get(n):return zero if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    request=crossings(t,get('REQUEST'));drop=crossings(t,get('REQUEST'),False);clk=crossings(t,get('CLK'))
    prep=crossings(t,get('PREPARE'));mask=crossings(t,get('RESET_N'))
    if len(request)!=2 or len(drop)!=1 or len(clk)!=7:raise ValueError('Wrong counter stimulus/clock epoch')
    counts={};latencies={}
    for name,edges,required in [('prepare',prep,2),('public_release',mask,3)]:
        if len(edges)!=1:raise ValueError(name+' rising-event count')
        prior=clk[(clk>request[0])&(clk<edges[0])];counts[name]=len(prior)
        latencies[name]=float(edges[0]-prior[-1]) if len(prior) else None
    stopped=t>=20000;level=1.8*spec['stop_level']
    if np.max(np.abs(get('CLK')[stopped]-level))>.18:raise ValueError('Clock did not remain stopped')
    final=t>=24000;cleared=all(float(np.max(np.abs(get(n)[final])))<=.18 for n in ['PREPARE','RESET_N'])
    before=t<request[0];held=all(float(np.max(np.abs(get(n)[before])))<=.18 for n in ['PREPARE','RESET_N'])
    falls={n:crossings(t,get(n),False).tolist() for n in ['PREPARE','RESET_N']}
    async_clear=cleared and all(len(v)==1 and drop[0]<v[0]<request[1] for v in falls.values())
    stress=[]
    for d in mos:
        values=[get(n) for n in d['terminals']]
        peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    half=500000/spec['mhz'];windows=all(v is not None and 0<v<half for v in latencies.values())
    passed=bool(held and counts==dict(prepare=2,public_release=3) and windows and async_clear and all(d['passed'] for d in stress))
    return dict(prepare_time_ps=float(prep[0]),public_release_time_ps=float(mask[0]),clock_edges_before_transition=counts,
        latency_from_qualifying_clock_ps=latencies,margin_to_next_half_phase_ps={k:half-v if v is not None else None for k,v in latencies.items()},
        held_before_request_passed=held,stopped_clock_clear_and_reassert_passed=bool(async_clear),
        terminal_stress=stress,terminal_screen_passed=all(d['passed'] for d in stress),counter_feasibility_passed=passed,
        qualified_phy=False,scope='Isolated source guarded-FF counter with real RC buffers/NAND input loads; no actual DCC first-event, custom-cell RC, full-PVT or PHY admission')


def prepare(targets,nands,clock):
    if engine()!='ngspice':raise ValueError('Explicitly select pinned ngspice')
    proof=json.loads((targets/'summary.json').read_text());i=proof['identity']
    if (i['version']!=diagnosis.VERSION or targets.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or not proof['all_violations_have_private_candidates'] or len(proof['rows'])!=8):raise ValueError('Require complete private-guard target diagnosis')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Guard-target witness changed')
    library=Path(i['source_library']);guard_nodes=proof['selected_private_nodes']
    parent_model=json.loads((ROOT/i['parent']/'manifest.json').read_text())
    if proof['base_guard_nodes']!=parent_model['identity']['guard_nodes'] or not set(proof['base_guard_nodes'])<=set(guard_nodes):raise ValueError('Retain all previously diagnosed startup guards')
    if sha(library)!=i['source_library_sha256']:raise ValueError('Native FF source library changed')
    rc={};paths=[targets/'summary.json',*[ROOT/n for n in i['inputs']]]
    for parent in [nands,clock]:
        group,files=components.witnesses(parent)
        if set(group)&set(rc):raise ValueError('Duplicate native RC model')
        rc.update(group);paths+=files
    cells='\n'.join(rc[n]['text'].rstrip() for n in sorted(rc))+'\n';variants={};ds={}
    for size in [1,2]:
        text=circuit.source(library.read_text(),rc,guard_nodes,size)+harness(rc);variants[size]=text
        ds[str(size)]=circuit.components.mapped_mos(cells+text,HARNESS,
            dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
    code=[Path(__file__),Path(circuit.__file__),Path(diagnosis.__file__),Path(components.__file__),ROOT/'scripts/native_clock_components_v3.py',
        ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/native_static_cells_v2.py',ROOT/'scripts/dcc_nand_mid_shunt_v2.py',
        ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',
        ROOT/'scripts/spice_slots.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',ROOT/'build/tools/ngspice.json',ROOT/'clocking_v2.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';models=[library,pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,targets=str(targets.relative_to(ROOT)),families=[str(n.relative_to(ROOT)) for n in [nands,clock]],guard_nodes=guard_nodes,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},pdk_files={str(p):sha(p) for p in models},
        source_library=str(library),simulator=provenance(),specs=specifications(),devices=ds)
    out=ROOT/'build/diagnostics/guarded_clock_prepare_v3'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells)
    for size,text in variants.items():write(out/f'guard{size}.spice',text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,ds[str(spec['guard_um'])]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/guarded_clock_prepare_v3' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):raise ValueError('Guarded prepare pilot changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Guarded prepare task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior guarded prepare campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='guarded_clock_prepare_v2_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'][str(task['spec']['guard_um'])])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='guarded_prepare_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--nands',type=Path);p.add_argument('--clock-cells',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':
        if a.nands is None or a.clock_cells is None:p.error('Provide both certified native RC families')
        print(prepare(out,a.nands.resolve(),a.clock_cells.resolve()),flush=True)
    else:run(out)
