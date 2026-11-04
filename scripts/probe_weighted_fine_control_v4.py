#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test weighted fine-control repair at fixed supply and both data biases.

Use all five independently verified physical fine-cell RC models with native
MOS/MIM geometry. Intercell wires remain ideal; no full-bank or PHY proof.
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
import weighted_fine_control_v3 as circuit
import weighted_fine_repair_rc_families_v2 as fine_families
import probe_weighted_fine_bank_v2 as failed
import phase_release_rc_families_v2 as families
from build_compound_drivers_v3 import cell_definition
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=failed.ROOT
VERSION='isolated-root-fine-double-tg-physical-and-driver-rc-v2.3'
CONTEXT='weighted_fine_control_v4'
CODES=[0,31,0,16,15,0]
STOP=12e-9


def specifications():return [dict(variant=v,process='ss',temperature=40,data_v=d,codes=list(CODES),control_slew_ps=20) for v,d in itertools.product(circuit.MODES,[0.,1.8])]


def libraries(clock,fines,repair,sc):
    rc,paths=families.witnesses(clock)
    cells,files=fine_families.witnesses(fines,repair)
    if set(rc)&set(cells):raise ValueError('Duplicate fine/control native model')
    rc.update(cells);paths+=files
    orders={n:c['info']['ports'] for n,c in rc.items()};texts=[rc[n]['text'].rstrip() for n in sorted(rc)]
    for short in ['buf_1','inv_1']:
        model=circuit.fine.old.native.SC+short;text=cell_definition(sc.read_text(),model);texts.append(text.rstrip());orders[model]=circuit.native.base.definitions(text)[model][0]
    modules={v+'.spice':circuit.source(v,orders) for v in circuit.MODES};cells='\n'.join(texts)+'\n'
    ds={v:circuit.devices(cells+modules[v+'.spice']) for v in circuit.MODES};modules['cells.spice']=cells
    return modules,orders,ds,paths


def fixture(out,spec,witness):
    devices=witness['mos']
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/cells.spice"',f'.include "{out}/{spec["variant"]}.spice"',
          f'.options device temp={spec["temperature"]}','.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8',f'VDATA DATA 0 {spec["data_v"]}']
    half=spec['control_slew_ps']/2000
    for bit in range(5):
        values=[1.8 if (c>>bit)&1 else 0 for c in spec['codes']];points=[f'0 {values[0]}']
        for j in range(1,len(values)):points += [f'{2*j-half:g}n {values[j-1]}',f'{2*j+half:g}n {values[j]}']
        rows.append(f'VB{bit} B{bit} 0 PWL('+' '.join(points)+')')
    rows += ['XD '+' '.join('0' if p=='VSS' else p for p in circuit.PORTS)+' '+circuit.NAME,'.tran 1p 12n 0 1p']
    probes={'DATA','VDD',*[f'B{i}' for i in range(5)],*[n+str(i) for i in range(5) for n in ['EN','ENB']],*[n for nodes in witness['cap_nodes'].values() for n in nodes]}
    probes.update(n for d in devices for n in d['terminals'] if n!='0')
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def measure(folder,spec,witness):
    devices=witness['mos']
    required={'v('+n.replace(':','.').lower()+')' for d in devices for n in d['terminals'] if n!='0'}
    required.update({'v(data)','v(vdd)',*[f'v({p}{i})' for i in range(5) for p in ['b','en','enb']],*['v('+n.replace(':','.').lower()+')' for nodes in witness['cap_nodes'].values() for n in nodes]})
    names,w=validate(folder/'bench.raw',required,STOP);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
    def get(n):return zero if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    if np.max(np.abs(get('VDD')-1.8))>1e-9 or np.max(np.abs(get('DATA')-spec['data_v']))>1e-9:raise ValueError('Fixed supply/data bias changed')
    settled=[]
    for j,code in enumerate(spec['codes']):
        window=(t>=2000*j+1500)&(t<=2000*j+1900)
        if not np.any(window):raise ValueError('Missing settled control window')
        for bit in range(5):
            target=1.8 if (code>>bit)&1 else 0
            if np.max(np.abs(get('B'+str(bit))[window]-target))>1e-9:raise ValueError('Control stimulus changed')
            peak=max(float(np.max(np.abs(get('EN'+str(bit))[window]-target))),float(np.max(np.abs(get('ENB'+str(bit))[window]-(1.8-target)))))
            cap=spec['data_v'] if target else 0.;cap_error=max(float(np.max(np.abs(get(n)[window]-cap))) for n in witness['cap_nodes'][str(bit)])
            settled.append(dict(code=code,bit=bit,cap_nodes=len(witness['cap_nodes'][str(bit)]),driver_error_v=peak,cap_error_v=cap_error,passed=peak<=.18 and cap_error<=.18))
    stress=[];worst=None;global_peak=0.
    for d in devices:
        values=[get(n) for n in d['terminals']];peak=0.
        for a,b in itertools.combinations(range(4),2):
            delta=np.abs(values[a]-values[b]);v=float(np.max(delta));peak=max(peak,v)
            if v>global_peak:
                j=int(np.argmax(delta));global_peak=v;worst=dict(device=d['name'],model=d['model'],terminal_pair=[a,b],nodes=[d['terminals'][a],d['terminals'][b]],time_ps=float(t[j]),voltages_v=[float(values[a][j]),float(values[b][j])])
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    logic=all(r['passed'] for r in settled);safe=all(r['passed'] for r in stress)
    return dict(settled_controls=settled,control_settling_passed=logic,terminal_stress=stress,terminal_screen_passed=safe,
        maximum_terminal_difference_v=global_peak,worst_terminal=worst,component_pilot_passed=logic and safe,qualified_phy=False,
        scope='Four SS40 20ps-control fixed-1.8V isolated driver/fine-load bias cases; actual repaired fine-cell RC and guarded-driver RC, source reference drivers and ideal intercell wires; no active-clock, full-bank range, full-PVT or PHY admission')


def prepare(clock,fines,baseline,repair):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice engine')
    bm=failed.bound(baseline);folder=baseline/'0';r=json.loads((folder/'summary.json').read_text())
    if r['task']!=bm['tasks'][0] or r['error'] is not None or r['result']['terminal_screen_passed']:raise ValueError('Require retained completed weighted-bank terminal failure')
    if any(sha(folder/n)!=h for n,h in r['files'].items()):raise ValueError('Completed failure witness changed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    modules,orders,ds,paths=libraries(clock,fines,repair,sc)
    code=[Path(__file__),Path(circuit.__file__),Path(circuit.base.__file__),Path(circuit.unit.__file__),Path(fine_families.__file__),Path(fine_families.original.__file__),Path(fine_families.verification.__file__),Path(failed.__file__),Path(families.__file__),ROOT/'scripts/dcdl_weighted_fine_v2.py',ROOT/'scripts/native_clock_components_v3.py',ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    paths += code+[baseline/'manifest.json',folder/'summary.json',*[folder/n for n in r['files']]]+[ROOT/n for n in bm['identity']['inputs']]
    models=[sc,pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,clock=str(clock.relative_to(ROOT)),fine_cells=str(fines.relative_to(ROOT)),repair=str(repair.relative_to(ROOT)),baseline=str(baseline.relative_to(ROOT)),source_library=str(sc),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files={str(p):sha(p) for p in models},simulator=provenance(),specs=specifications(),orders=orders,devices=ds)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    for n,text in modules.items():write(out/n,text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        f=out/str(n);f.mkdir();write(f/'bench.cir',fixture(out,spec,ds[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(f/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in modules},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['specs']!=specifications()
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=4):raise ValueError('Fine-control pilot context changed')
    for n,t in enumerate(m['tasks']):
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=t['deck_sha256']:raise ValueError('Fine-control deck/task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior fine-control run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            f=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(f/'ngspice.log'),str(f/'bench.cir')],capture_output=True,text=True)
                write(f/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(f,task['spec'],m['identity']['devices'][task['spec']['variant']])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in f.iterdir() if p.is_file()});atomic(f/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='fine_control_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--baseline',type=Path);p.add_argument('--fine-cells',type=Path);p.add_argument('--repair',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.baseline is None or a.fine_cells is None or a.repair is None:p.error('Provide the fine RC receipt and retained full-bank failure parent')
        print(prepare(a.artifact.resolve(),a.fine_cells.resolve(),a.baseline.resolve(),a.repair.resolve()),flush=True)
    else:run(a.artifact.resolve())
