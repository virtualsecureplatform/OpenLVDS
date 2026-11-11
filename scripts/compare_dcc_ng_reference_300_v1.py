#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete ngspice controls for strict Xyce baseline and repaired DCC points."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import xyce_profile_300 as xyce
import qualify_dcc_xyce_300_v1 as dcc
from run_native_binary_v2 import translate
from native_binary_raw_v2 import validate
from spice_dispatch import lease
from replay_bank_300_v2 import same

ROOT=xyce.ROOT
CONTEXT='dcc_ng_reference_300_v1'
PARENT=ROOT/'build/diagnostics/dcc_xyce_300_v1/b12dc12b493548ab'


def prepare():
    m=json.loads((PARENT/'manifest.json').read_text())
    ng=ROOT/'build/tools/ngspice.json'
    inputs={**m['identity']['inputs'],str(PARENT/'manifest.json'):xyce.sha(PARENT/'manifest.json'),str(ng):xyce.sha(ng)}
    inputs.update({str(ROOT/n):h for n,h in json.loads(ng.read_text())['files'].items()})
    for p in {Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'}|{Path(__file__).resolve()}:
        inputs[str(p)]=xyce.sha(p)
    identity=dict(version=CONTEXT,inputs=inputs,parent=str(PARENT.relative_to(ROOT)),selected=['2','5','26','29'],max_workers=2,priority=2,timeout_seconds=900,qualified_phy=False)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True,exist_ok=False)
    tasks=[]
    for number in identity['selected']:
        t=next(t for t in m['tasks'] if t['id']==number)
        folder=out/number
        folder.mkdir()
        text=(PARENT/number/'bench.cir').read_text()
        text=re.sub(r'(?m)^\.options (parser|nonlin) .*\n','',text)
        text=re.sub(r'(?m)^\.print tran format=raw precision=17 file=\S+ ','.print tran ',text)
        text,names=translate(text)
        text=text.replace('.end\n',f'.control\nset num_threads = 1\nset filetype = binary\nrun\nwrite {folder}/bench.raw all\n.endc\n.end\n')
        (folder/'bench.cir').write_text(text)
        tasks.append(dict(parent_task=t,deck_sha256=xyce.sha(folder/'bench.cir'),names=['time',*names]))
    dcc.save(out/'manifest.json',dict(identity=identity,tasks=tasks))
    return out


def run(out):
    m=json.loads((out/'manifest.json').read_text())
    for n,h in m['identity']['inputs'].items():
        if xyce.sha(n)!=h:
            raise ValueError('Captured reference input changed: '+n)
    with (out/'state.json').open('x') as f:
        json.dump(dict(status='running',qualified_phy=False),f)
    def one(task):
        t=task['parent_task'];folder=out/t['id'];row=dict(task=task,error=None,complete=False)
        start=time.monotonic()
        try:
            if xyce.sha(folder/'bench.cir')!=task['deck_sha256']:
                raise ValueError('Deck changed')
            runtime=ROOT/'build/tools/ngspice-runtime'
            command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-o',str(folder/'native.log'),str(folder/'bench.cir')]
            row['command']=command
            with lease(ROOT,priority=2,label=CONTEXT+'_'+t['id']):
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run(command,cwd=folder,env=xyce.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=900)
                row['returncode']=p.returncode
                if p.returncode:
                    raise ValueError('ngspice returned '+str(p.returncode))
            names,w=validate(folder/'bench.raw',set(task['names']),t['stop'])
            result=dcc.measure(names,w,t['spec'],t['observations'])
            independent=dcc.measure(names,w,t['spec'],t['observations'],True)
            if not same(result,independent):
                raise ValueError('Independent native reference differs')
            row.update(complete=True,result=result)
        except Exception as exc:
            row['error']=str(exc)
        row['wall_seconds']=time.monotonic()-start
        row['files']={p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()}
        dcc.save(folder/'summary.json',row)
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,t) for t in m['tasks']]):
            rows.append(future.result())
            dcc.save(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    for n,h in m['identity']['inputs'].items():
        if xyce.sha(n)!=h:
            raise ValueError('Reference input changed during simulation: '+n)
    dcc.save(out/'summary.json',dict(rows=rows,qualified_phy=False,scope='Strict native ngspice controls for four source-DCC points only'))
    dcc.save(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run'])
    p.add_argument('artifact',type=Path,nargs='?')
    a=p.parse_args()
    if a.action=='prepare':
        print(prepare(),flush=True)
    elif a.artifact is None:
        p.error('Supply fresh artifact')
    else:
        run(a.artifact.resolve())
