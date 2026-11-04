#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare five weighted fine switches using real compound-core RC.

This SS/40 C architecture pilot retains all coarse stages and actual extracted
core cells. Fine devices, native control cells, shared MIM and common wiring
are source-only. It cannot admit physical timing or a legal-code ROM.
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
import dcdl_weighted_fine_v2 as circuit
import extract_compound_drivers_v2 as core
from audit_passive_rc_v3 import audit
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=core.ROOT
VERSION='weighted-five-bit-fine-bank-native-core-rc-pilot-v2.1'
CODES=[0,1,16,31,0]


def specifications():
    return [dict(variant=v,process='ss',temperature=40,coarse=c,codes=CODES,control_slew_ps=20,input_slew_ps=100,load_ff=20)
            for v,c in itertools.product(circuit.SCALES,[0,1])]


def fixture(out,spec,mos):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/cells.spice"',
          f'.include "{out}/{spec["variant"]}.spice"',f'.options device temp={spec["temperature"]}',
          '.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8']
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    pulses=[f'0.9*(tanh((time-{10*i+2.1:g}n)/{width:.17g})-tanh((time-{10*i+6.1:g}n)/{width:.17g}))' for i in range(len(spec['codes']))]
    rows.append('BIN IN 0 V={'+'+'.join(pulses)+'}')
    for bit in range(15):rows.append(f'VC{bit} C{bit} 0 '+str(1.8 if bit<spec['coarse'] else 0))
    for bit in range(5):
        values=[1.8 if (code>>bit)&1 else 0 for code in spec['codes']];points=[f'0 {values[0]}'];half=spec['control_slew_ps']/2000
        for i in range(1,len(values)):points += [f'{10*i-half:g}n {values[i-1]}',f'{10*i+half:g}n {values[i]}']
        rows.append(f'VB{bit} B{bit} 0 PWL('+' '.join(points)+')')
    rows += ['XD '+' '.join('0' if p=='VSS' else p for p in circuit.PORTS)+' '+circuit.NAME,
             f'CLOAD OUT 0 {spec["load_ff"]}f',f'.tran 2p {10*len(spec["codes"])}n 0 2p']
    probes={'IN','OUT','VDD','XD:r0',*[f'B{i}' for i in range(5)],*[f'C{i}' for i in range(15)],
            *[f'XD:fine{i}' for i in range(5)],*[f'XD:fine_b{i}' for i in range(5)],*[f'XD:coarse{i}' for i in range(15)]}
    probes.update(n for d in mos for n in d['terminals'] if n!='0')
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def measure(folder,spec,mos):
    required={'v(in)','v(out)',*[('v('+n.replace(':','.').lower()+')') for d in mos for n in d['terminals'] if n!='0']}
    names,w=validate(folder/'bench.raw',required,len(spec['codes'])*10e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;zeros=np.zeros(len(t))
    def get(n):return zeros if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    samples=[];controls=[]
    for i,code in enumerate(spec['codes']):
        base=i*10000;window=(t>=base)&(t<=base+10000);stable=(t>=base+1500)&(t<base+9500);sample=dict(code=code)
        for up,label in [(True,'rise'),(False,'fall')]:
            a=crossings(t[window],get('IN')[window],up);b=crossings(t[window],get('OUT')[window],up)
            if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra weighted-bank pulse or wrong epoch')
            sample[label+'_delay_ps']=float(b[0]-a[0])
        worst=0.
        for bit in range(15):
            target=1.8 if bit<spec['coarse'] else 0
            if np.max(np.abs(get(f'C{bit}')[stable]-target))>.01:raise ValueError('Weighted-bank coarse stimulus changed during pulse')
            worst=max(worst,float(np.max(np.abs(get(f'XD:coarse{bit}')[stable]-target))))
        for bit in range(5):
            target=1.8 if (code>>bit)&1 else 0
            if np.max(np.abs(get(f'B{bit}')[stable]-target))>.01:raise ValueError('Weighted-bank control stimulus changed during pulse')
            worst=max(worst,float(np.max(np.abs(get(f'XD:fine{bit}')[stable]-target))),
                      float(np.max(np.abs(get(f'XD:fine_b{bit}')[stable]-(1.8-target)))))
        if worst>.18:raise ValueError('Weighted-bank internal control violates logic margins')
        controls.append(dict(code=code,internal_max_deviation_v=worst));samples.append(sample)
    stress=[]
    for d in mos:
        values=[get(n) for n in d['terminals']]
        peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=1.95,passed=peak<=1.95))
    return dict(samples=samples,controls=controls,terminal_stress=stress,terminal_screen_passed=all(d['passed'] for d in stress),
        minimum_quarter_headroom_ps=1e6/410/4-max(s[k+'_delay_ps'] for s in samples if s['code']==0 for k in ['rise','fall']) if spec['coarse']==0 else None,
        qualified_phy=False,legal_code_table_admitted=False,
        scope='SS40 sparse weighted-fine source devices plus native compound-core RC; no common-wire/control/fine-layout RC, dense code, full-PVT or PHY admission')


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Select the pinned ngspice engine explicitly')
    pm=core.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if not report['passed'] or len(report['rows'])!=4:raise ValueError('Require all four native core RC/topology proofs')
    cells=[];orders={};paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json']
    for row in report['rows']:
        info=row['extraction'];text=checked_netlist(info)
        if not row['rc_topology_passed'] or not audit(text)['elementwise_passive_passed']:raise ValueError('Require passive native compound RC')
        cells.append(text);orders[row['macro']]=info['ports'];paths += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/row['macro']/'lvs.log']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice';library=sc.read_text()
    for short in ['conb_1','buf_4','buf_1','inv_1']:
        model=circuit.old.native.SC+short;text=core.physical.cell_definition(library,model);cells.append(text)
        orders[model]=circuit.parsing.definitions(text)[model][0]
    cell_text='\n'.join(cells);variants={v:circuit.fine_cells(v)+circuit.source(v,orders) for v in circuit.SCALES}
    mos={v:circuit.mapped_mos(cell_text+variants[v]) for v in variants}
    paths += [Path(__file__),Path(circuit.__file__),Path(core.__file__),ROOT/'scripts/dcdl_mim_bank_physical_v2.py',ROOT/'scripts/dcdl_mim_bank_v2.py',
        ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_library.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_slots.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/reduce_rc.py',ROOT/'clocking_v2.json',ROOT/'requirements.json',ROOT/'build/tools/ngspice.json']
    models=[sc,pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files={str(p):sha(p) for p in models},
        simulator=provenance(),specs=specifications(),devices=mos,orders=orders,total_fine_mim_area_um2=186,maximum_step_ps=2)
    out=ROOT/'build/diagnostics/weighted_fine_bank_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cell_text)
    for v,text in variants.items():write(out/(v+'.spice'),text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,mos[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/weighted_fine_bank_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):raise ValueError('Weighted-bank pilot identity changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Weighted-bank deck/task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior weighted-bank run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='weighted_fine_bank_v2_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'][task['spec']['variant']])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='weighted_bank_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    else:run(out)
