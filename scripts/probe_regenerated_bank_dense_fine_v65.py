#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""All SS40 fine codes at coarse 0/1 after independently verified routed sparse pass."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_regenerated_bank_joint_zero_v61 as zero
import verify_regenerated_bank_sparse_v64 as proof
import probe_regenerated_bank_sparse_v63 as sparse
import regenerated_bank_dense_metrics_v65 as metrics

ROOT=zero.ROOT
sha=zero.sha
VERSION='regenerated-actual-joint-rc-ss40-dense-fine-two-coarse-selections-v65.1'
CONTEXT='regenerated_bank_dense_fine_v65'
SCOPE='64 SS40 native fine-code points at coarse 0/1 on the same actual joint RC; no full-coarse-range/update/periodic/all-PVT, legal table, electrical or PHY admission'


def specifications():return [dict(zero.spec(),coarse=c,fine=f) for c,f in metrics.FRESH_CODES]


def inherited(evidence):
    binding=proof.bound(evidence);receipt=json.loads((evidence/'summary.json').read_text())
    if not receipt['complete_sparse_bank_screen_passed']:raise ValueError('Require independent complete routed sparse pass')
    parent=ROOT/binding['parent'];m=sparse.bound(parent)
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=5,errors=0,qualified_phy=False):
        raise ValueError('Require all five original sparse tasks complete')
    rows=[dict(spec=zero.spec(),result=m['identity']['zero_result'],error=None),*receipt['rows']]
    if not metrics.sparse.compare(rows)['sparse_native_screen_passed']:raise ValueError('Inherited sparse comparison changed')
    return parent,m,receipt


def fixture(out,i,s):
    text=zero.fixture(out,dict(i,spec=s));title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed zero fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(evidence):
    parent,m,receipt=inherited(evidence);old=m['identity'];binding=json.loads((evidence/'manifest.json').read_text())['identity']
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in binding['inputs']],parent/'bank.spice']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),sparse_parent=str(parent.relative_to(ROOT)),
        specs=specifications(),top=old['top'],ports=old['ports'],model=old['model'],observations=old['observations'],
        netlist=old['netlist'],pdk_files=old['pdk_files'],simulator=old['simulator'],cad=old['cad'],
        inherited_rows=[dict(spec=zero.spec(),result=old['zero_result'],error=None),*receipt['rows']],inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);zero.baseline.write(out/'bank.spice',(parent/'bank.spice').read_text());tasks=[]
    for n,s in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();zero.baseline.write(folder/'bench.cir',fixture(out,identity,s))
        tasks.append(dict(id=str(n),spec=s,deck_sha256=sha(folder/'bench.cir')))
    zero.baseline.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={'bank.spice':sha(out/'bank.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];o=i['observations']
    original=json.loads((ROOT/i['sparse_parent']/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or i['max_workers']!=2 or zero.engine()!='ngspice' or zero.provenance()!=i['simulator']
            or len(o['devices'])!=951 or len(o['programming_gates'])!=133 or o['observed_canonical_nets']!=150
            or any(i[k]!=original[k] for k in ('top','ports','model','observations','netlist','pdk_files','simulator','cad'))
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
            or sha(Path(i['cad']['path']))!=i['cad']['sha256'] or sha(out/'bank.spice')!=m['libraries']['bank.spice']
            or (out/'bank.spice').read_bytes()!=(ROOT/i['netlist']).read_bytes()
            or len(m['tasks'])!=len(i['specs'])):raise ValueError('Regenerated SS40 dense-fine context changed')
    evidence=json.loads((ROOT/i['evidence']/'summary.json').read_text())
    if (not evidence['complete_sparse_bank_screen_passed'] or i['inherited_rows']!=[dict(spec=zero.spec(),result=original['zero_result'],error=None),*evidence['rows']]):raise ValueError('Inherited routed sparse points changed')
    for n,t in enumerate(m['tasks']):
        deck=out/str(n)/'bench.cir'
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or t['deck_sha256']!=sha(deck) or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Dense fine code or native fixture changed')
    return m


def measure(folder,i,s):
    result=sparse.measure(folder,i,s)
    result['scope']=SCOPE
    return result


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial dense-fine campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                zero.baseline.write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=i['max_workers']) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        comparison=None
        if all(r['error'] is None for r in rows):comparison=metrics.compare([*i['inherited_rows'],*rows])
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=comparison,qualified_phy=False,scope=SCOPE))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
