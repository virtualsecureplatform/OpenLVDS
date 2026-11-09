#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate a measured decoder DC discrepancy; never admit a whole backend.

No supply or input sweep. Fixed captured input values, exact original native
cells, two sparse solvers and three explicit numerical precision settings.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_smp_origin_300_v1 as reference
import run_native_binary_v2 as klu
import run_native_smp_binary_300_v1 as smp
import native_clock_components_v2 as native
from native_binary_raw_v2 import validate
from dcc_source_300 import model_closure
from spice_dispatch import lease

ROOT=reference.ROOT
PARENT=ROOT/'build/diagnostics/smp_origin_pilot_300_v1/9585a6f64e2cd7c3'
VERSION='isolated-exact-source-decoder-dc-precision-300-v1'
CONTEXT='decoder_dc_solver_pilot_300_v1'
CELL='sky130_fd_sc_hd__and2_4'
INV='sky130_fd_sc_hd__inv_4'
SETTINGS={'native':'.options timeint method=gear reltol=1e-4 abstol=1e-12',
    'tight_current':'.options timeint method=gear reltol=1e-4 abstol=1e-18 vntol=1e-10',
    'tight_all':'.options timeint method=gear reltol=1e-10 abstol=1e-20 vntol=1e-11'}
sha=reference.sha
atomic=reference.atomic
SCOPE='Exact-source isolated decoder DC diagnosis only; no bank timing, backend transfer, combined chain or PHY admission'


def library(text):
    parts=[]
    for name in (CELL,INV):
        pattern=r'(?ims)^\.subckt\s+'+re.escape(name)+r'\s[^\n]*\n.*?^\.ends\b[^\n]*'
        found=re.findall(pattern,text)
        if len(found)!=1:raise ValueError('Require one exact original decoder/inverter definition')
        parts.append(found[0])
    return '\n'.join(parts)+'\n'


def fixture(out,setting,values,model):
    if setting not in SETTINGS or set(values)!={'A','B'} or not all(np.isfinite(v) and 0<=v<=1.8 for v in values.values()):
        raise ValueError('Undeclared precision setting or captured input')
    text=(f'OpenLVDS {VERSION}\n.lib "{model}" ss\n.include "{out}/cells.spice"\n'
        '.options device temp=40\n'+SETTINGS[setting]+'\nVDD VDD 0 1.8\n'
        f'VA A 0 {values["A"]:.17g}\nVB B 0 {values["B"]:.17g}\n'
        f'XD A B 0 0 VDD VDD X {CELL}\nXI X 0 0 VDD VDD Y {INV}\n'
        '.tran .1p 2p 0 .1p\n')
    defs=native.definitions((out/'cells.spice').read_text())
    nodes={'A','B','VDD','X','Y'}
    for instance,name,mapping in [('XD',CELL,dict(A='A',B='B',VGND='0',VNB='0',VPB='VDD',VPWR='VDD',X='X')),
                                  ('XI',INV,dict(A='X',VGND='0',VNB='0',VPB='VDD',VPWR='VDD',Y='Y'))]:
        # SKY130 inv output is Y, while the AND output is X.
        if set(mapping)!=set(defs[name][0]):raise ValueError('Captured decoder port order changed')
        devices=native.mapped_mos((out/'cells.spice').read_text(),name,mapping,instance)
        nodes.update(n for d in devices for n in d['terminals'] if n!='0')
    text+='.print tran '+' '.join('V('+n+')' for n in sorted(nodes))+'\n.end\n'
    klu.translate(text);smp.translate(text)
    return text


def prepare():
    m=reference.bound(PARENT,full=False);row=json.loads((PARENT/'0/summary.json').read_text())
    if row['error'] is not None or row['task']!=m['tasks'][0] or row['parity']['passed'] is not False or row['parity']['maximum_dc_voltage_error_v']<=1e-9:
        raise ValueError('Require the complete failed SMP DC comparison')
    paths=[PARENT/'manifest.json',PARENT/'bank.spice',PARENT/'0/summary.json']
    for n,h in row['files'].items():
        if Path(n).name!=n or sha(PARENT/'0'/n)!=h:raise ValueError('SMP failure witness changed')
        paths.append(PARENT/'0'/n)
    names,w=validate(PARENT/'0/bench.raw',{'v(xd.select_b0)','v(xd.select1)'},40e-9)
    values=dict(A=float(w[0,names.index('v(xd.select_b0)')]),B=float(w[0,names.index('v(xd.select1)')]))
    if w[0,names.index('time')]!=0:raise ValueError('SMP reference omits DC')
    text=(PARENT/'0/bench.cir').read_text()
    model=re.search(r'(?m)^\.lib "([^"\n]+)" ss$',text)
    if model is None:raise ValueError('Reference process changed')
    code=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    paths+=code+[ROOT/'build/tools/ngspice.json',ROOT/'clocking_300mhz.json']
    paths+=[ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    inputs={str(p):sha(p) for p in paths}
    inputs.update(model_closure(Path(model[1])))
    identity=dict(version=VERSION,inputs=inputs,guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},
        settings=SETTINGS,values=values,model=model[1],process='ss',temperature=40,stop_ps=2,
        max_workers=1,priority=2,supply_sweep=False,scope=SCOPE,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'cells.spice').write_text(library((PARENT/'bank.spice').read_text()))
    tasks=[]
    for setting in SETTINGS:
        for backend in ('klu','smp'):
            task=dict(id=str(len(tasks)),setting=setting,backend=backend)
            folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(fixture(out,setting,values,model[1]))
            tasks.append(dict(task,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,library_sha256=sha(out/'cells.spice'),qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['settings']!=SETTINGS or i['scope']!=SCOPE or (i['max_workers'],i['priority'])!=(1,2)
            or i['supply_sweep'] is not False or i['qualified_phy'] is not False or m['qualified_phy'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or (i['process'],i['temperature'],i['stop_ps'])!=('ss',40,2)):
        raise ValueError('Isolated decoder precision identity changed')
    if any(sha(Path(n))!=h for n,h in (i['inputs'] if full else i['guards']).items()):raise ValueError('Decoder source witness changed')
    if sha(out/'cells.spice')!=m['library_sha256'] or (out/'cells.spice').read_text()!=library((PARENT/'bank.spice').read_text()):
        raise ValueError('Original decoder/inverter bytes changed')
    tasks=[]
    for setting in SETTINGS:
        for backend in ('klu','smp'):
            folder=out/str(len(tasks));deck=fixture(out,setting,i['values'],i['model'])
            if (folder/'bench.cir').read_text()!=deck:raise ValueError('Decoder precision fixture changed')
            tasks.append(dict(id=folder.name,setting=setting,backend=backend,deck_sha256=sha(folder/'bench.cir')))
    if m['tasks']!=tasks:raise ValueError('Incomplete precision/backend coverage')
    return m


def measure(folder):
    names,w=validate(folder/'bench.raw',{'v(xd.a_110_47#)','v(a)','v(b)','v(x)','v(y)','v(vdd)'},2e-12)
    if w[0,names.index('time')]!=0:raise ValueError('Decoder trace omits native DC')
    volts=[k for k,n in enumerate(names) if n!='time'];dc={names[k]:float(w[0,k]) for k in volts}
    return dict(dc=dc,maximum_static_drift_v=float(np.max(np.abs(w[:,volts]-w[0,volts]))),
                stack_node_dc_v=dc['v(xd.a_110_47#)'],qualified_phy=False)


def comparisons(rows):
    expected=[(str(k),s,b) for k,(s,b) in enumerate((s,b) for s in SETTINGS for b in ('klu','smp'))]
    if [(r['task']['id'],r['task']['setting'],r['task']['backend']) for r in rows]!=expected:
        raise ValueError('Require all six exact source precision/backend cases')
    result={}
    for k,s in enumerate(SETTINGS):
        a,b=rows[2*k:2*k+2]
        if a['error'] is not None or b['error'] is not None:
            result[s]=dict(complete=False,dc_agrees_within_1nv=False);continue
        av=a['result']['dc'];bv=b['result']['dc']
        if av.keys()!=bv.keys():raise ValueError('Decoder saved DC vectors differ')
        errors={n:abs(av[n]-bv[n]) for n in av};worst=max(errors,key=errors.get)
        result[s]=dict(complete=True,maximum_dc_difference_v=errors[worst],worst_vector=worst,
            dc_agrees_within_1nv=errors[worst]<=1e-9)
    return result


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior isolated decoder evidence')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    helper='run_native_binary_v2.py' if task['backend']=='klu' else 'run_native_smp_binary_300_v1.py'
                    p=subprocess.run([sys.executable,str(ROOT/'scripts'/helper),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(folder)
            except Exception as exc:error=str(exc)
            rows.append(dict(task=task,error=error,result=result,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()}))
            atomic(folder/'summary.json',rows[-1]);atomic(out/'progress.json',dict(completed=len(rows),qualified_phy=False))
        bound(out);atomic(out/'summary.json',dict(rows=rows,comparisons=comparisons(rows),backend_admitted=False,
            combined_circuit_admitted=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=6,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured decoder precision artifact')
        print(run(a.artifact.resolve()),flush=True)
