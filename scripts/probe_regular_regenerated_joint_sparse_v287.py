#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend a passing actual routed joint-RC zero trace to coarse/fine overlap.

All three points retain the identical physical bank and full native observations.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import probe_regular_regenerated_joint_zero_v286 as native

ROOT=native.ROOT
zero=native.zero
sha=native.sha
VERSION='actual-regular-pair-p20n16-joint-rc-zero-coarse-fine-full-native-v287.1'
CONTEXT='regular_regenerated_joint_sparse_v287'
SCOPE='Actual regular-pair P20/N16 routed joint-RC SS/40 three-point screen: consumed passing zero plus new fine31/coarse1, all native observations and both pulses; dense/update/periodic/PVT/electrical/PHY remain unqualified'


def specifications(spec):return [dict(spec,coarse=c,fine=f) for c,f in ((0,31),(1,0))]


def fixture(out,i,s):
    text=native.fixture(out,dict(i,spec=s))
    title='OpenLVDS '+native.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original sparse native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    fi=native.bound(parent);r=json.loads((parent/'summary.json').read_text());case=parent/'0';row=json.loads((case/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
        or r['rows']!=[row] or row['error'] is not None
        or row['spec']!=fi['spec'] or fi['spec']!=native.spec()
        or not row['result']['joint_rc_zero_screen_passed'] or not row['result']['whole_bank_rc_retained']
        or any(sha(case/n)!=h for n,h in row['files'].items()) or native.measure(case,fi)!=row['result']):
        raise ValueError('Require complete unchanged passing actual joint-RC zero trace')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json','bank.spice']]
    paths += [case/'summary.json',*[case/n for n in row['files']],*[ROOT/n for n in fi['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(fi,version=VERSION,source_zero=str(parent.relative_to(ROOT)),source_zero_result=row['result'],specs=specifications(fi['spec']),
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
        or i['spec']!=native.spec() or sha(Path(native.CAD))!=i['cad']['sha256']
        or i['specs']!=specifications(i['spec']) or len(m['tasks'])!=2
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['source_zero']/'bank.spice')!=m['bank_sha256']):
        raise ValueError('Actual joint-RC sparse context changed')
    row=json.loads((ROOT/i['source_zero']/'0/summary.json').read_text())
    if row['error'] is not None or row['result']!=i['source_zero_result']:raise ValueError('Consumed actual joint-RC zero result changed')
    for k,t in enumerate(m['tasks']):
        deck=out/str(k)/'bench.cir'
        if t['id']!=str(k) or t['spec']!=i['specs'][k] or sha(deck)!=t['deck_sha256'] or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Actual joint-RC sparse fixture changed')
    return m


def measure(folder,i):
    result=native.measure(folder,i)
    # Quarter-period budget applies only to the already-admitted zero code.
    result.pop('zero_code_fast_quarter_headroom_ps')
    result.pop('joint_rc_zero_screen_passed')
    return dict(result,joint_rc_sparse_point_passed=bool(result['static_native_screen_passed'] and result['output_slew_domain_passed']),scope=SCOPE)


def compare(rows,zero_result):
    if len(rows)!=2 or any(row['error'] is not None for row in rows):return None
    by={(row['spec']['coarse'],row['spec']['fine']):row['result'] for row in rows}
    if set(by)!={(0,31),(1,0)}:raise ValueError('Actual joint-RC sparse case coverage changed')
    if any(len(r['samples'])!=2 for r in [zero_result,*by.values()]):raise ValueError('Require both complete pulse epochs')
    if any(set(p)!={'rise_delay_ps','fall_delay_ps'} or any(not math.isfinite(v) or v<=0 for v in p.values()) for r in [zero_result,*by.values()] for p in r['samples']):raise ValueError('Invalid native pulse delay')
    overlaps=[{edge+'_ps':by[0,31]['samples'][k][edge+'_delay_ps']-by[1,0]['samples'][k][edge+'_delay_ps'] for edge in ['rise','fall']} for k in range(2)]
    monotonic=all(r['samples'][k][edge+'_delay_ps']>zero_result['samples'][k][edge+'_delay_ps'] for r in by.values() for k in range(2) for edge in ['rise','fall'])
    native_ok=zero_result['joint_rc_zero_screen_passed'] and all(r['joint_rc_sparse_point_passed'] for r in by.values())
    whole=all(r['whole_bank_rc_retained'] for r in [zero_result,*by.values()])
    conservative={edge:min(r[edge+'_delay_ps'] for r in by[0,31]['samples'])-max(r[edge+'_delay_ps'] for r in by[1,0]['samples']) for edge in ('rise','fall')}
    return dict(conservative_coarse_overlap_ps=conservative,coarse_overlap_by_pulse=overlaps,positive_progress_from_zero=monotonic,
                zero_code_fast_quarter_headroom_ps=zero_result['zero_code_fast_quarter_headroom_ps'],
                joint_rc_sparse_feasibility_passed=bool(native_ok and whole and monotonic and all(v>0 for p in overlaps for v in p.values()) and all(v>0 for v in conservative.values())),
                complete_zero_trace_consumed=True,whole_bank_rc_retained=whole,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial actual joint-RC sparse campaign')
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
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows,i['source_zero_result']),source_zero=i['source_zero'],scope=SCOPE,qualified_phy=False))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=2,consumed_zero_cases=1,errors=sum(row['error'] is not None for row in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
