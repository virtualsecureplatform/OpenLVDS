#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched original/shunted native NAND2-pair idle, pulse and stress experiment."""
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
import time
import numpy as np
import forward_guard_rc_families_v2 as families
import native_clock_components_v2 as native
import diagnose_dcdl_iterations_v2 as diagnosis
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=families.ROOT
VERSION='matched-native-forward-pair-idle-pulse-stress-v2.1'
CONTEXT='forward_pair_v2'
MODELS={'shunted':'openlvds_nand2_4_o3_shunted_pair_v2','original':'openlvds_nand2_4_pair_v2'}
STOP=20e-9
EDGES_PS=[2100.,6100.,12100.,16100.]
PIN_MAP=dict(A='A',B='B',Y='Y',VPWR='VDD',VGND='0')


def specifications():
    return [dict(variant=v,toggle_pin=pin,process='ss',temperature=40,input_slew_ps=100,load_ff=20)
            for v,pin in itertools.product(MODELS,['B','A'])]


def libraries(original,shunted):
    cells={};paths=[]
    for parent in [original,shunted]:
        group,files=families.witnesses(parent)
        if set(cells)&set(group):raise ValueError('Duplicate native forward-pair model')
        cells.update(group);paths+=files
    modules={};orders={};devices={}
    for variant,model in MODELS.items():
        if model not in cells:raise ValueError('Missing exact native forward pair')
        cell=cells[model];ports=cell['info']['ports']
        if len(ports)!=5 or set(ports)!=set(PIN_MAP):raise ValueError('Native NAND2 pair interface changed')
        modules[variant+'.spice']=cell['text'];orders[variant]=ports
        devices[variant]=native.mapped_mos(cell['text'],model,PIN_MAP,'XG')
        if len(devices[variant])!=32:raise ValueError('Require all 32 original native MOS per pair')
    return modules,orders,devices,paths


def stimulus(t,spec):
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    return sum(.9*(np.tanh((t-a*1e-12)/width)-np.tanh((t-b*1e-12)/width))
               for a,b in zip(EDGES_PS[::2],EDGES_PS[1::2]))


def fixture(out,spec,orders,devices):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/{spec["variant"]}.spice"',
          f'.options device temp={spec["temperature"]}', '.options itl4=100',
          '.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8']
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    terms=[f'0.9*(tanh((time-{a/1000:g}n)/{width:.17g})-tanh((time-{b/1000:g}n)/{width:.17g}))'
           for a,b in zip(EDGES_PS[::2],EDGES_PS[1::2])]
    pin=spec['toggle_pin'];other='A' if pin=='B' else 'B'
    rows += [f'B{pin} {pin} 0 V={{'+ '+'.join(terms)+'}',f'V{other} {other} 0 1.8',
             'XG '+' '.join(PIN_MAP[p] for p in orders)+' '+MODELS[spec['variant']],
             f'CLOAD Y 0 {spec["load_ff"]}f','.tran 1p 20n 0 1p']
    probes={'A','B','Y','VDD',*[n for d in devices for n in d['terminals'] if n!='0']}
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def measure(folder,spec,devices):
    required={'v(a)','v(b)','v(y)','v(vdd)',*['v('+n.replace(':','.').lower()+')' for d in devices for n in d['terminals'] if n!='0']}
    names,w=validate(folder/'bench.raw',required,STOP);index={n:i for i,n in enumerate(names)};t=w[:,index['time']];ps=t*1e12;zero=np.zeros(len(t))
    def get(n):return zero if n=='0' else w[:,index['v('+n.replace(':','.').lower()+')']]
    pin=spec['toggle_pin'];other='A' if pin=='B' else 'B'
    if (np.max(np.abs(get('VDD')-1.8))>1e-9 or np.max(np.abs(get(other)-1.8))>1e-9
        or np.max(np.abs(get(pin)-stimulus(t,spec)))>1e-9):raise ValueError('Matched supply/input waveform changed')
    source=sorted([(float(v),True) for v in crossings(ps,get(pin),True)]+[(float(v),False) for v in crossings(ps,get(pin),False)])
    if len(source)!=4 or any(abs(v-expected)>.01 for (v,_),expected in zip(source,EDGES_PS)):
        raise ValueError('Missing or shifted native stimulus events')
    output={True:crossings(ps,get('Y'),True),False:crossings(ps,get('Y'),False)}
    all_output=sorted([float(v) for values in output.values() for v in values]);events=[]
    for j,(edge,up) in enumerate(source):
        end=source[j+1][0] if j+1<len(source) else STOP*1e12
        selected=[v for v in all_output if edge<v<end]
        correct=[float(v) for v in output[not up] if edge<v<end]
        ok=len(selected)==len(correct)==1
        events.append(dict(input_edge_ps=edge,input_rising=up,output_edge='fall' if up else 'rise',
                           output_edges=len(selected),delay_ps=correct[0]-edge if ok else None,passed=ok))
    windows=[(1000.,1800.,1.8)]+[(edge+1500.,(source[j+1][0] if j+1<len(source) else 20000.)-200.,0. if up else 1.8)
                                       for j,(edge,up) in enumerate(source)]
    settled=[]
    for start,end,target in windows:
        select=(ps>=start)&(ps<=end)
        if not np.any(select):raise ValueError('Missing native settled-output window')
        error=float(np.max(np.abs(get('Y')[select]-target)))
        settled.append(dict(start_ps=start,end_ps=end,target_v=target,maximum_error_v=error,passed=error<=.18))
    stress=[];peak=0.;worst=None;idle=(t<=1e-9);idle_span=0.
    if not np.any(idle):raise ValueError('Missing initial static-bias interval')
    for d in devices:
        values=[get(n) for n in d['terminals']];device_peak=0.
        idle_span=max(idle_span,max(float(np.ptp(v[idle])) for v in values))
        for a,b in itertools.combinations(range(4),2):
            difference=np.abs(values[a]-values[b]);value=float(np.max(difference));device_peak=max(device_peak,value)
            if value>peak:
                k=int(np.argmax(difference));peak=value
                worst=dict(device=d['name'],terminal_pair=[a,b],nodes=[d['terminals'][a],d['terminals'][b]],time_ps=float(ps[k]))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=device_peak,limit_v=d['limit_v'],passed=device_peak<=d['limit_v']))
    event_ok=len(all_output)==4 and all(e['passed'] for e in events);logic=all(s['passed'] for s in settled);safe=all(s['passed'] for s in stress)
    return dict(events=events,settled=settled,terminal_stress=stress,maximum_terminal_difference_v=peak,worst_terminal=worst,
                preinput_native_terminal_excursion_v=idle_span,event_integrity_passed=event_ok,logic_passed=logic,terminal_screen_passed=safe,
                isolated_pilot_passed=event_ok and logic and safe,qualified_phy=False,
                scope='Matched isolated SS40 native 32-MOS pair with fixed 1.8 V supply, 20 fF load and two pulses on A or B; ideal upstream sources; no bank convergence, PVT, code ROM or PHY admission')


def prepare(original,shunted,failure_context):
    if engine()!='ngspice':raise ValueError('Require explicitly pinned ngspice')
    proof=json.loads((failure_context/'summary.json').read_text());fi=proof['identity']
    if (failure_context.parent!=ROOT/'build/diagnostics/dcdl_iteration_failure_v2' or fi['version']!=diagnosis.VERSION
        or failure_context.name!=hashlib.sha256(json.dumps(fi,sort_keys=True).encode()).hexdigest()[:16]
        or not proof['diagnosis_verified'] or not proof['partial_payloads_bit_identical'] or proof['iteration_increase_resolved_failure']
        or any(sha(ROOT/n)!=h for n,h in fi['inputs'].items())):raise ValueError('Require retained matched pre-input failure evidence')
    modules,orders,devices,paths=libraries(original,shunted)
    code=[Path(__file__),Path(families.__file__),Path(native.__file__),Path(diagnosis.__file__),ROOT/'scripts/native_binary_raw_v2.py',
          ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    paths+=code+[failure_context/'summary.json']+[ROOT/n for n in fi['inputs']]
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    pdks=[pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').rglob('*.spice'))
    identity=dict(version=VERSION,original=str(original.relative_to(ROOT)),shunted=str(shunted.relative_to(ROOT)),failure_context=str(failure_context.relative_to(ROOT)),
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files={str(p):sha(p) for p in pdks},simulator=provenance(),specs=specifications(),orders=orders,devices=devices)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    for name,text in modules.items():write(out/name,text)
    tasks=[]
    for k,spec in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,orders[spec['variant']],devices[spec['variant']]))
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in modules},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['specs']!=specifications()
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=4):raise ValueError('Native forward-pair context changed')
    for k,task in enumerate(m['tasks']):
        if task['id']!=str(k) or task['spec']!=i['specs'][k] or sha(out/str(k)/'bench.cir')!=task['deck_sha256']:raise ValueError('Native forward-pair task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous pair experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None;elapsed=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    process=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    elapsed=time.monotonic()-start
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'][task['spec']['variant']])
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,solver_wall_seconds=elapsed,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='forward_pair_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--shunted',type=Path);p.add_argument('--failure-context',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.shunted is None or a.failure_context is None:p.error('Provide shunted RC and retained failure context')
        print(prepare(a.artifact.resolve(),a.shunted.resolve(),a.failure_context.resolve()),flush=True)
    else:run(a.artifact.resolve())
