#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Six-point actual routed fine-boundary screen with conservative pulse intervals.

Consumes admitted zero/coarse/fine31 traces and adds fine1/15/16. Dense tables,
all-PVT ordering, periodic/update timing and PHY admission remain separate.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_measured_balanced_joint_sparse_v153 as sparse
import math

native=sparse.native

ROOT=native.ROOT
zero=native.zero
sha=native.sha
VERSION='actual-measured-balanced-joint-rc-six-point-conservative-fine-boundaries-v158.1'
CONTEXT='measured_balanced_joint_boundaries_v158'
SCOPE='Six actual routed SS/40 code points with full native observations, conservative both-pulse fine boundaries and coarse overlap; dense/common legal tables, full range, update/periodic/all-PVT/electrical/PHY remain unqualified'
CODES=((0,0),(0,1),(0,15),(0,16),(0,31),(1,0))


def specifications(spec):return [dict(spec,coarse=0,fine=f) for f in (1,15,16)]


def fixture(out,i,s):
    text=native.fixture(out,dict(i,spec=s));title='OpenLVDS '+native.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original complete native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    source=sparse.bound(parent);fi=source['identity'];r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=2,consumed_zero_cases=1,errors=0,qualified_phy=False)
        or len(r['rows'])!=2 or r['comparison']!=sparse.compare(r['rows'],fi['source_zero_result'])
        or not r['comparison']['joint_rc_sparse_feasibility_passed']):
        raise ValueError('Require complete passing actual joint-RC sparse screen')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json','bank.spice']]
    paths += [ROOT/n for n in fi['inputs']]
    for task,row in zip(source['tasks'],r['rows']):
        case=parent/task['id']
        if (row!=json.loads((case/'summary.json').read_text()) or row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None
            or any(sha(case/n)!=h for n,h in row['files'].items()) or sparse.measure(case,dict(fi,spec=task['spec']))!=row['result']):
            raise ValueError('Actual sparse native result does not reproduce')
        paths += [case/'summary.json',*[case/n for n in row['files']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(fi,version=VERSION,source_sparse=str(parent.relative_to(ROOT)),source_sparse_result=r['comparison'],specs=specifications(fi['spec']),
           inherited_rows=[dict(spec=fi['spec'],result=fi['source_zero_result'],error=None),*r['rows']],
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for k,s in enumerate(i['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,i,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    (out/'manifest.json').write_text(json.dumps(dict(identity=i,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or zero.engine()!='ngspice' or zero.provenance()!=i['simulator'] or i['max_workers']!=2
        or i['spec']!=native.spec(i['profile']) or sha(Path(native.CAD))!=i['cad']['sha256']
        or i['specs']!=specifications(i['spec']) or len(m['tasks'])!=3
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['source_sparse']/'bank.spice')!=m['bank_sha256']):
        raise ValueError('Actual joint-RC fine-boundary context changed')
    receipt=json.loads((ROOT/i['source_sparse']/'summary.json').read_text())
    if receipt['comparison']!=i['source_sparse_result'] or not receipt['comparison']['joint_rc_sparse_feasibility_passed']:
        raise ValueError('Consumed actual sparse result changed')
    origin=json.loads((ROOT/i['source_sparse']/'manifest.json').read_text())['identity']
    if i['inherited_rows']!=[dict(spec=origin['spec'],result=origin['source_zero_result'],error=None),*receipt['rows']]:raise ValueError('Consumed native code-point rows changed')
    for k,t in enumerate(m['tasks']):
        deck=out/str(k)/'bench.cir'
        if t['id']!=str(k) or t['spec']!=i['specs'][k] or sha(deck)!=t['deck_sha256'] or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Actual joint-RC fine-boundary fixture changed')
    return m


def measure(folder,i):return dict(sparse.measure(folder,i),scope=SCOPE)


def compare(rows):
    if len(rows)!=6 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    points={};profile=rows[0]['spec']['profile']
    if profile not in ('b2','b3'):raise ValueError('Unknown physical profile')
    for row in rows:
        s=row['spec'];key=s['coarse'],s['fine'];r=row['result']
        if key in points or key not in CODES or s!=dict(native.spec(profile),coarse=key[0],fine=key[1]):raise ValueError('Six-point native code/PVT coverage changed')
        if (len(r['samples'])!=2 or any(set(v)!={'rise_delay_ps','fall_delay_ps'} or any(not math.isfinite(x) or x<=0 for x in v.values()) for v in r['samples'])):
            raise ValueError('Require both complete finite native pulse epochs')
        points[key]=r
    if set(points)!=set(CODES):raise ValueError('Incomplete native boundary coverage')
    def interval(code,edge):
        values=[s[edge+'_delay_ps'] for s in points[code]['samples']]
        return min(values),max(values)
    steps=[];overlap={}
    for edge in ('rise','fall'):
        for a,b in ((0,1),(1,15),(15,16),(16,31)):
            lo,hi=interval((0,a),edge);right_lo,right_hi=interval((0,b),edge)
            steps.append(dict(edge=edge,from_fine=a,to_fine=b,minimum_change_ps=right_lo-hi,maximum_change_ps=right_hi-lo,
                              conservative_order_passed=right_lo>hi,adjacent_gap_passed=0<right_lo-hi and right_hi-lo<=20 if b-a==1 else None))
        fine_lo,_=interval((0,31),edge);_,coarse_hi=interval((1,0),edge);overlap[edge+'_ps']=fine_lo-coarse_hi
    z=points[0,0];headroom=z['zero_code_fast_quarter_headroom_ps']
    zero_ok=bool(z['joint_rc_zero_screen_passed'] and math.isfinite(headroom) and headroom>=0)
    whole=all(r['whole_bank_rc_retained'] for r in points.values())
    native_ok=all(r['static_native_screen_passed'] and r['output_slew_domain_passed'] for r in points.values())
    order=all(s['conservative_order_passed'] for s in steps)
    gaps=all(s['adjacent_gap_passed'] is not False for s in steps)
    coarse=all(v>0 for v in overlap.values())
    return dict(completed_points=6,steps=steps,conservative_coarse_overlap=overlap,zero_code_fast_quarter_headroom_ps=headroom,
                sampled_conservative_order_passed=order,sampled_adjacent_20ps_gaps_passed=gaps,
                six_point_native_screen_passed=bool(whole and native_ok and zero_ok and order and gaps and coarse),
                whole_bank_rc_retained=whole,dense_legal_code_coverage_proven=False,legal_code_table_admitted=False,
                all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial actual joint-RC fine-boundary campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,dict(i,spec=task['spec']))
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=compare([*i['inherited_rows'],*rows]),source_sparse=i['source_sparse'],scope=SCOPE,qualified_phy=False))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=3,consumed_cases=3,errors=sum(row['error'] is not None for row in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
