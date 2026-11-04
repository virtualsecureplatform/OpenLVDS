#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native whole-bank RC minimum-delay and coarse/fine overlap pilot.

Two isolated pulses at each static thermometer code retain absolute edge epochs.
Every extracted MOS terminal is saved and screened. This sparse pilot does not
admit a code ROM, code updates, full PVT, periodic-clock operation or the PHY.
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
import extract_dcdl_bank_rc_v2 as extraction
import native_clock_components_v2 as parsing
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=extraction.ROOT
VERSION='whole-routed-dcdl-bank-static-code-pulse-pilot-v2.1'
STOP=20e-9


def specifications():
    return [dict(process=p,temperature=t,coarse=c,fine=f,load_ff=20,input_slew_ps=100)
            for (p,t),(c,f) in itertools.product([('ss',40),('ff',0)],[(0,0),(0,31),(1,0)])]


def devices(text):
    defs=parsing.definitions(text)
    if len(defs)!=1:raise ValueError('Require a single flat bank RC model')
    name,(ports,body)=next(iter(defs.items()));result=[]
    for w in body:
        if w[0][0].upper() in ['R','C']:continue
        if w[0][0].upper()!='X':raise ValueError('Unknown extracted bank element')
        end=next((i for i,v in enumerate(w) if '=' in v),len(w));model=w[end-1];nodes=w[1:end-1]
        if model in ['sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8','sky130_fd_pr__pfet_01v8_hvt']:
            if len(nodes)!=4:raise ValueError('Wrong bank MOS terminal count')
            mapping={p:('0' if p=='VGND' else 'VDD' if p=='VPWR' else p) for p in ports}
            result.append(dict(name='XD:'+w[0],model=model,limit_v=1.95,
                               terminals=[mapping.get(n,'XD:'+n) for n in nodes]))
        elif model.startswith('sky130_fd_pr__') and ('cap_mim_' in model or 'res_generic_' in model or 'diode_' in model):continue
        else:raise ValueError('Unknown active bank device '+model)
    if not result:raise ValueError('Missing native bank MOS devices')
    return name,ports,result


def fixture(out,spec,text):
    top,ports,mos=devices(text)
    if spec['coarse'] not in range(16) or spec['fine'] not in range(32):raise ValueError('Invalid physical-bank code')
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/bank_rc.spice"',
          f'.options device temp={spec["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12',
          'VDD VDD 0 1.8']
    # tanh rise/fall each has exactly the specified 10--90% slew.
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    pulses=[f'0.9*(tanh((time-{base+2.1:g}n)/{width:.17g})-tanh((time-{base+6.1:g}n)/{width:.17g}))' for base in [0,10]]
    rows+=['BIN IN 0 V={'+'+'.join(pulses)+'}']
    for p in ports:
        if p.startswith(('C','E')) and p[1:].isdigit():
            level=1.8 if int(p[1:])<spec['coarse' if p[0]=='C' else 'fine'] else 0
            rows.append('V'+p+' '+p+' 0 '+str(level))
    mapping={p:('0' if p=='VGND' else 'VDD' if p=='VPWR' else p) for p in ports}
    rows+=['XD '+' '.join(mapping[p] for p in ports)+' '+top,f'CLOAD OUT 0 {spec["load_ff"]}f',
           '.tran 2p 20n 0 2p']
    probes=sorted({'IN','OUT','VDD',*[n for d in mos for n in d['terminals'] if n!='0'],
                   *[p for p in ports if p.startswith(('C','E')) and p[1:].isdigit()]})
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in probes),'.end',''])


def measure(folder,spec,mos):
    requested={'v(in)','v(out)','v(vdd)',*[('v('+n.replace(':','.').lower()+')') for d in mos for n in d['terminals'] if n!='0']}
    names,w=validate(folder/'bench.raw',requested,STOP);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    zeros=np.zeros(len(t))
    def get(n):return zeros if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    samples=[]
    for base in [0,10000]:
        select=(t>=base)&(t<=base+10000);time=t[select];sample=dict(pulse=base//10000)
        for up,label in [(True,'rise'),(False,'fall')]:
            a=crossings(time,get('IN')[select],up);b=crossings(time,get('OUT')[select],up)
            if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra routed pulse or wrong epoch')
            sample[label+'_delay_ps']=float(b[0]-a[0])
        samples.append(sample)
    controls=[]
    for prefix,count,key in [('C',15,'coarse'),('E',31,'fine')]:
        for bit in range(count):
            target=1.8 if bit<spec[key] else 0
            deviation=float(np.max(np.abs(get(prefix+str(bit))-target)))
            if deviation>.01:raise ValueError('Routed-bank control stimulus changed')
            controls.append(dict(pin=prefix+str(bit),max_deviation_v=deviation))
    stress=[]
    for d in mos:
        values=[get(n) for n in d['terminals']]
        peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    quarter=[1e6/410/4,1e6/390/4]
    return dict(samples=samples,controls=controls,terminal_stress=stress,terminal_screen_passed=all(d['passed'] for d in stress),
        repeated_delay_difference_ps={k:abs(samples[1][k+'_delay_ps']-samples[0][k+'_delay_ps']) for k in ['rise','fall']},
        required_quarter_range_ps=quarter,
        minimum_below_fast_quarter=all(s[k+'_delay_ps']<quarter[0] for s in samples for k in ['rise','fall']) if spec['coarse']==spec['fine']==0 else None,
        native_pulse_passed=all(d['passed'] for d in stress),qualified_phy=False,legal_code_table_admitted=False,
        scope='Two static-code isolated pulses through the full routed bank; no dense code/update, full-PVT, periodic clock or PHY admission')


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Use the explicitly selected pinned ngspice engine')
    # Physical receipts bind the tools-Python executable. Validate under that
    # exact interpreter, then use scientific Python for waveform work.
    pm=json.loads((parent/'manifest.json').read_text())
    physical_python=pm['identity']['tools']['python']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_dcdl_bank_rc_v2 as e; e.bound(Path(sys.argv[2]))'
    subprocess.run([physical_python,'-c',code,str(ROOT),str(parent)],check=True)
    report=json.loads((parent/'summary.json').read_text());info=report['extraction']
    if not all(report.get(k) for k in ['passed','rc_topology_passed','power_grid_verified','interface_verified']):raise ValueError('Require complete native bank RC proof')
    if not info['passivity']['elementwise_passive_passed']:raise ValueError('Require positive-element bank RC')
    text=checked_netlist(info);_,_,mos=devices(text)
    inputs=[parent/n for n in ['manifest.json','summary.json','state.json','native_reference.spice','native_instance_counts.json','lvs.log','power_grid.log']]
    inputs += [ROOT/info['netlist'],ROOT/info['raw_netlist']]
    code=[Path(__file__),Path(parsing.__file__),Path(extraction.__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/run_native_binary_v2.py',
          ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_library.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_slots.py',
          ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/reduce_rc.py',ROOT/'clocking_v2.json',ROOT/'requirements.json',
          ROOT/'build/tools/ngspice.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';models=[pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs+code},
        pdk_files={str(p):sha(p) for p in models},simulator=provenance(),specs=specifications(),devices=mos,maximum_step_ps=2)
    out=ROOT/'build/diagnostics/routed_dcdl_bank_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'bank_rc.spice',text);tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,text))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_rc_sha256=sha(out/'bank_rc.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.parent!=ROOT/'build/diagnostics/routed_dcdl_bank_v2'
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or engine()!='ngspice' or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or sha(out/'bank_rc.spice')!=m['bank_rc_sha256']):raise ValueError('Routed-bank pilot inputs changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Routed-bank task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior routed-bank campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='routed_dcdl_bank_v2_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='routed_bank_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='bound':print(json.dumps(bound(out),indent=2))
    else:run(out)
