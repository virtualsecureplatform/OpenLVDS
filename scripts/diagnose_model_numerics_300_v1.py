#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Separate time-integration tolerance and input smoothness at fixed supplies."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import xyce_profile_300 as xyce
import qualify_models_xyce_300_v2 as model
from dcc_source_300 import model_closure
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize
from spice_dispatch import lease
from qualify_dcc_xyce_300_v1 import save

ROOT=xyce.ROOT
CONTEXT='model_numerics_300_v1'


def specs():
    values=[dict(engine='xyce',reltol=1e-5,nonlin_abstol=1e-12,timeint_abstol=a) for a in [1e-12,1e-10,1e-9,1e-8]]
    values += [dict(engine='xyce',reltol=1e-4,nonlin_abstol=1e-9,timeint_abstol=1e-9),
               dict(engine='ngspice',reltol=1e-5,nonlin_abstol=1e-12,timeint_abstol=None),
               dict(engine='ngspice',reltol=1e-4,nonlin_abstol=1e-9,timeint_abstol=None)]
    return [dict(s,waveform=w) for w in ['pwl','smooth'] for s in values]


def fixture(folder,spec):
    text=model.deck(folder,'tt',25,spec['engine'])
    if spec['engine']=='xyce':
        text=re.sub(r'(?m)^\.options nonlin .*$',f'.options nonlin reltol={spec["reltol"]} abstol={spec["nonlin_abstol"]}',text)
        text=re.sub(r'(?m)^\.options timeint .*$',f'.options timeint method=gear reltol={spec["reltol"]} abstol={spec["timeint_abstol"]}',text)
    else:
        text=re.sub(r'(?m)^\.options klu .*$',f'.options klu method=gear reltol={spec["reltol"]} abstol={spec["nonlin_abstol"]}',text)
    if spec['waveform']=='smooth':
        for name,node,voltage in [('VIN','IN',1.8),('VIN33','IN33',3.3)]:
            terms=[]
            # Same 50% epochs and 20/250 ps 10-90 slews as the PWL control.
            for rise,fall,slew in [(1.0125e-9,2.5125e-9,20e-12),(4.15625e-9,5.65625e-9,250e-12)]:
                sigma=slew/(2*math.atanh(.8))
                terms.append(f'{voltage/2}*(tanh((time-{rise:.17g})/{sigma:.17g})-tanh((time-{fall:.17g})/{sigma:.17g}))')
            text,count=re.subn(r'(?m)^'+name+r' '+node+r' 0 PWL\([^\n]+\)$','B'+name+' '+node+' 0 V={'+ '+'.join(terms)+'}',text)
            if count!=1:
                raise ValueError('Model input source changed')
    return text


def prepare():
    runtime=xyce.runtime()
    inputs=model_closure(model.PDK/'libs.tech/ngspice/sky130.lib.spice')
    ng=ROOT/'build/tools/ngspice.json'
    inputs[str(ng)]=xyce.sha(ng)
    inputs.update({str(ROOT/n):h for n,h in json.loads(ng.read_text())['files'].items()})
    helpers={Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'}|{Path(__file__).resolve()}
    inputs.update({str(p):xyce.sha(p) for p in helpers})
    identity=dict(version=CONTEXT,inputs=inputs,runtime=runtime,specs=specs(),max_workers=2,priority=2,timeout_seconds=90,qualified_models=False)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True,exist_ok=False)
    tasks=[]
    for k,spec in enumerate(specs()):
        folder=out/str(k);folder.mkdir()
        (folder/'bench.cir').write_text(fixture(folder,spec))
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=xyce.sha(folder/'bench.cir')))
    save(out/'manifest.json',dict(identity=identity,tasks=tasks))
    return out


def run(out):
    m=json.loads((out/'manifest.json').read_text())
    def bound():
        if m['identity']['runtime']!=xyce.runtime():
            raise ValueError('Runtime changed')
        files={**m['identity']['inputs'],**m['identity']['runtime']['files']}
        files.update({str(out/t['id']/'bench.cir'):t['deck_sha256'] for t in m['tasks']})
        for name,h in files.items():
            if xyce.sha(name)!=h:
                raise ValueError('Captured input changed: '+name)
    bound()
    with (out/'state.json').open('x') as f:json.dump(dict(status='running',qualified_models=False),f)
    def one(task):
        folder=out/task['id'];engine=task['spec']['engine'];row=dict(task=task,error=None,complete=False)
        start=time.monotonic()
        try:
            if engine=='xyce':
                command=xyce.command(folder/'native.log',folder/'bench.cir')
            else:
                runtime=ROOT/'build/tools/ngspice-runtime'
                command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-o',str(folder/'native.log'),str(folder/'bench.cir')]
            row['command']=command
            with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run(command,cwd=folder,env=xyce.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=90)
                row['returncode']=p.returncode
                if p.returncode:raise ValueError('Simulator returned '+str(p.returncode))
            if engine=='xyce':row['normalization']=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            names,w=validate(folder/'bench.raw',{'v('+n+')' for n in model.NODES},model.STOP)
            row.update(complete=True,records=len(w))
        except Exception as exc:row['error']=str(exc)
        row['wall_seconds']=time.monotonic()-start
        row['warnings']=xyce.warnings('\n'.join(p.read_text(errors='replace') for p in [folder/'console.log',folder/'native.log'] if p.exists()))
        row['files']={p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()}
        save(folder/'summary.json',row)
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,t) for t in m['tasks']]):
            rows.append(future.result());save(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),total=14))
    bound();rows.sort(key=lambda r:int(r['task']['id']))
    save(out/'summary.json',dict(rows=rows,qualified_models=False,qualified_phy=False))
    save(out/'state.json',dict(status='complete',cases=14,errors=sum(r['error'] is not None for r in rows)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Supply artifact')
    else:run(a.artifact.resolve())
