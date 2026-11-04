#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Dense native fine-code characterization using isolated tagged pulse windows.

Amortize native model elaboration across eight codes, with the input held low
while controls change. The MIM geometry is unchanged; only return merge drive
increases from NAND4 to NAND8. No waveform prefix or failed point is reused.
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
import dcdl_cap_strong_v2 as policy
import probe_digital_dcdl_v2 as original

h=original.helpers
ROOT=h.ROOT
VERSION='dense-dcdl-mim-strong-return-batch-v2.1'
WINDOW_PS=10000


def fixture(out,spec):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    text=(f'OpenLVDS {VERSION} unwrapped pulse windows\n.lib "{model}" {spec["process"]}\n'
        f'.include "{out}/cells.spice"\n.include "{out}/coarse{spec["coarse"]}.spice"\n'
        f'.options device temp={spec["temperature"]}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VDD VDD 0 1.8\n')
    pulses=[]
    for i,_ in enumerate(spec['codes']):
        base=i*10
        pulses.append(f'0.9*(tanh((time-{base+2.1}n)/72.819138130147p)-tanh((time-{base+6.1}n)/72.819138130147p))')
    text+='BIN IN 0 V={'+'+'.join(pulses)+'}\n'
    for i in range(31):
        values=[1.8 if i<c else 0 for c in spec['codes']];points=[f'0 {values[0]}']
        for k in range(1,len(values)):
            points += [f'{10*k-.05:g}n {values[k-1]}',f'{10*k+.05:g}n {values[k]}']
        text+=f'VE{i} E{i} 0 PWL('+' '.join(points)+')\n'
        text+=f'XEB{i} E{i} 0 0 VDD VDD EB{i} sky130_fd_sc_hd__inv_1\n'
    text+='XD IN OUT VDD 0 '+' '.join(pin for i in range(31) for pin in (f'E{i}',f'EB{i}'))+' dcdl_source\n'
    text+='CLOAD OUT 0 20f\n'
    text+=f'.tran 2p {10*len(spec["codes"])}n 0 2p\n'
    probes=['IN','OUT','XD:f0','XD:r0','VDD']+[f'XD:cap{i}' for i in range(31)]+[n for i in range(31) for n in (f'E{i}',f'EB{i}')]
    return text+'.print tran '+' '.join(f'V({n})' for n in probes)+'\n.end\n'


def measure(folder,task):
    spec=task['spec'];names,w=h.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    stop=WINDOW_PS*len(spec['codes'])
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete batch waveform')
    get=lambda n: np.zeros(len(w)) if n=='VSS' else (w[:,names.index('v(vdd)')] if n=='VDD' else
        w[:,names.index('v('+('xd.'+n if n in ['r0','f0'] or n.startswith('cap') else n.lower())+')')])
    output=get('OUT');inp=get('IN');samples=[]
    for i,code in enumerate(spec['codes']):
        base=i*WINDOW_PS;select=(t>=base)&(t<=base+WINDOW_PS)
        time=t[select];a=inp[select];b=output[select];result=dict(code=code)
        for rising,label in [(True,'rise'),(False,'fall')]:
            first=h.crossings(time,a,rising);last=h.crossings(time,b,rising)
            if len(first)!=1 or len(last)!=1 or last[0]<=first[0]:
                raise ValueError(f'Missing/extra pulse or wrong epoch in fine code {code}')
            result[label+'_delay_ps']=float(last[0]-first[0])
        # Controls must be settled throughout the entire tagged pulse, including
        # the output tail. Codes are known thermometer patterns, never inferred.
        stable=(t>=base+1500)&(t<base+9500)
        for bit in range(31):
            expected=1.8 if bit<code else 0
            if np.max(np.abs(get(f'E{bit}')[stable]-expected))>.01 or np.max(np.abs(get(f'EB{bit}')[stable]-(1.8-expected)))>.01:
                raise ValueError('Fine control changed during a tagged pulse')
        samples.append(result)
    stress=[]
    for device in task['devices']:
        voltages=[get(n) for n in device['terminals']]
        maximum=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(voltages,2))
        stress.append(dict(device=device['name'],max_terminal_difference_v=maximum,limit_v=1.95,passed=maximum<=1.95))
    return dict(samples=samples,custom_mos_stress=stress,custom_mos_stress_passed=all(d['passed'] for d in stress),
        qualified_phy=False,scope='Dense source fine-code delay and custom MOS stress including code changes; no physical or DLL admission')


def prepare(parent):
    pm=original.bound(parent);pdk=Path(pm['identity']['pdk'])
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    files=[Path(__file__),ROOT/'scripts/dcdl_cap_strong_v2.py',ROOT/'scripts/dcdl_cap_bank_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',
        ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(process=p,temperature=t,coarse=c,codes=list(range(start,start+8)))
        for (p,t),c,start in itertools.product([('tt',25),('ss',40),('ff',0)],[0,1],[0,8,16,24])]
    identity=dict(version=VERSION,policy=policy.VERSION,parent=str(parent.relative_to(ROOT)),
        parent_manifest_sha256=h.sha(parent/'manifest.json'),code={str(p.relative_to(ROOT)):h.sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=h.sha(pdk),model_library=str(model),model_library_sha256=h.sha(model),
        simulator=h.provenance(),specs=specs,window_ps=WINDOW_PS,maximum_step_ps=2,load_ff=20)
    out=ROOT/'build/diagnostics/digital_dcdl_batch_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();cells=(parent/'cells.spice').read_text()
    for name in ['inv_1','nand2_8']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+name)
        cells+='\n'+found[0]+'\n'
    h.write(out/'cells.spice',cells)
    for coarse in [0,1]:h.write(out/f'coarse{coarse}.spice',policy.circuit(coarse)[0])
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,devices=policy.circuit(spec['coarse'])[1],deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcdl_batch_v2'):raise ValueError('Wrong dense batch context')
    m=h.bound(out);i=m['identity']
    if i['version']!=VERSION or i['policy']!=policy.VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']:
        raise ValueError('Dense batch context changed')
    if h.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']:raise ValueError('Parent context changed')
    for task in m['tasks']:
        if task['devices']!=policy.circuit(task['spec']['coarse'])[1] or (out/task['id']/'bench.cir').read_text()!=fixture(out,task['spec']):
            raise ValueError('Dense batch fixture changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior execution')
        h.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with original.lease(ROOT,priority=0,label='dcdl_dense_v2_'+task['id']):
                    bound(out);process=subprocess.run(original.command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                h.write(folder/'console.log',process.stdout+process.stderr);process.check_returncode();result=measure(folder,task)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:h.sha(p) for p in folder.iterdir() if p.is_file()})
            h.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);h.atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        h.atomic(out/'state.json',dict(status='source_screen_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='run':run(a.artifact.resolve())
    else:print(json.dumps(bound(a.artifact.resolve()),indent=2))
