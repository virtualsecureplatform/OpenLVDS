#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched output-compensation hypotheses on the retained actual bank network.

Removes only one/both identified output guard MIM devices. All MOS and existing
wire RC remain; changed compensation requires fresh physical/RC qualification.
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
import probe_measured_balanced_joint_sparse_v153 as source
import measured_bank_observations_v145 as aliases
import output_guard_variants_v159 as guards

native=source.native

ROOT=native.ROOT
zero=native.zero
sha=native.sha
VERSION='retained-actual-bank-shared-or-removed-output-compensation-hypotheses-v159.1'
CONTEXT='measured_output_guard_variants_v159'
SCOPE='Output compensation circuit hypotheses on retained baseline wire RC, full native MOS observations and unchanged 20 fF load; changed MIM geometry/interconnect unqualified, no bank/model/PVT/electrical/PHY admission'
VARIANTS={'shared':1,'none':0}


def specifications(spec):
    return [dict(variant=v,spec=dict(spec,coarse=c,fine=f)) for c,f in ((0,31),(0,0),(1,0)) for v in VARIANTS]


def bindings(parent,fi):
    rc=ROOT/fi['parent'];ri=json.loads((rc/'manifest.json').read_text())['identity'];rr=json.loads((rc/'summary.json').read_text())
    if not rr['joint_rc_passed'] or json.loads((rc/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False):raise ValueError('Original RC receipt did not pass')
    placement=ROOT/ri['placement']/'manifest.json';pi=json.loads(placement.read_text())['identity']
    mag=ROOT/ri['parent']/'native'/(fi['top']+'.mag');ext=(ROOT/rr['original_extraction']['raw_netlist']).parent/(fi['top']+'_rcx.ext')
    _,labelled,_,_=aliases.aliases(mag.read_text(),ext.read_text(),(parent/'bank.spice').read_text(),pi['graph'],pi['plan'])
    return labelled,[rc/'manifest.json',rc/'summary.json',rc/'state.json',placement,mag,ext]


def fixture(out,i,task):
    text=native.fixture(out/task['variant'],dict(i,spec=task['spec']))
    title='OpenLVDS '+native.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original sparse native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    m=source.bound(parent);fi=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=2,consumed_zero_cases=1,errors=0,qualified_phy=False)
        or len(r['rows'])!=2 or r['comparison']!=source.compare(r['rows'],fi['source_zero_result'])
        or r['comparison']['joint_rc_sparse_feasibility_passed']):raise ValueError('Require retained failed actual sparse screen')
    by={(row['spec']['coarse'],row['spec']['fine']):row for row in r['rows']}
    if (set(by)!={(0,31),(1,0)} or any(row['error'] is not None or not row['result']['static_native_screen_passed'] for row in r['rows'])
        or by[0,31]['result']['output_slew_domain_passed'] or by[0,31]['result']['maximum_output_slew_ps']<=250
        or not by[1,0]['result']['joint_rc_sparse_point_passed'] or not fi['source_zero_result']['joint_rc_zero_screen_passed']
        or not all(v>0 for pulse in r['comparison']['coarse_overlap_by_pulse'] for v in pulse.values())):
        raise ValueError('Require exactly the measured fine31 slew failure with retained zero/coarse/overlap safety')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json','bank.spice']]
    paths += [ROOT/n for n in fi['inputs']]
    for task,row in zip(m['tasks'],r['rows']):
        folder=parent/task['id']
        if (row['task']!=task or row!=json.loads((folder/'summary.json').read_text()) or any(sha(folder/n)!=h for n,h in row['files'].items())
            or source.measure(folder,dict(fi,spec=task['spec']))!=row['result']):raise ValueError('Retained native failure cannot reproduce')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    labelled,physical_files=bindings(parent,fi);paths+=physical_files
    designs={v:guards.variant((parent/'bank.spice').read_text(),fi['top'],labelled,keep) for v,keep in VARIANTS.items()}
    if any(p['original_native_mos']!=len(fi['observations']['devices']) or p['original_native_mims']!=42 for _,p in designs.values()):raise ValueError('Source native census changed')
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(fi,version=VERSION,source_failed=str(parent.relative_to(ROOT)),baseline_comparison=r['comparison'],specs=specifications(fi['spec']),
           guard_proofs={v:proof for v,(_,proof) in designs.items()},
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for v,(text,_) in designs.items():(out/v).mkdir();(out/v/'bank.spice').write_text(text)
    tasks=[]
    for k,task in enumerate(i['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,i,task))
        tasks.append(dict(task,id=str(k),deck_sha256=sha(folder/'bench.cir')))
    (out/'manifest.json').write_text(json.dumps(dict(identity=i,tasks=tasks,libraries={v:sha(out/v/'bank.spice') for v in designs},qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=ROOT/i['source_failed']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or zero.engine()!='ngspice' or zero.provenance()!=i['simulator'] or i['max_workers']!=2
        or i['spec']!=native.spec(i['profile']) or i['specs']!=specifications(i['spec']) or len(m['tasks'])!=6
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())):
        raise ValueError('Output-compensation hypothesis context changed')
    labelled,_=bindings(parent,i)
    for v,keep in VARIANTS.items():
        text,proof=guards.variant((parent/'bank.spice').read_text(),i['top'],labelled,keep)
        if proof!=i['guard_proofs'][v] or text!=(out/v/'bank.spice').read_text() or sha(out/v/'bank.spice')!=m['libraries'][v]:raise ValueError('Candidate changed original MOS/wire records or output-guard selection')
    for k,t in enumerate(m['tasks']):
        deck=out/str(k)/'bench.cir'
        if t!=dict(i['specs'][k],id=str(k),deck_sha256=sha(deck)) or deck.read_text()!=fixture(out,i,t):raise ValueError('Candidate variant or complete native fixture changed')
    return m


def measure(folder,i,s):
    r=source.measure(folder,dict(i,spec=s));point=r['joint_rc_sparse_point_passed'] and r['static_native_screen_passed'] and r['output_slew_domain_passed'];zero_code=s['coarse']==s['fine']==0
    headroom=1e6/410/4-max(v for sample in r['samples'] for v in sample.values()) if zero_code else None
    return dict(r,hypothesis_point_checks_passed=bool(point and (not zero_code or headroom>=0)),
                zero_code_fast_quarter_headroom_ps=headroom,joint_rc_sparse_point_passed=False,whole_bank_rc_retained=False,
                original_wire_rc_retained=True,candidate_layout_qualified=False,qualified_phy=False,scope=SCOPE)


def compare(rows):
    if len(rows)!=6 or any(r['error'] is not None for r in rows):return None
    result=[]
    for variant in VARIANTS:
        selected=[r for r in rows if r['task']['variant']==variant]
        by={(r['spec']['coarse'],r['spec']['fine']):r['result'] for r in selected}
        if len(selected)!=3 or set(by)!={(0,0),(0,31),(1,0)}:raise ValueError('Candidate code coverage changed')
        overlap=[{e+'_ps':by[0,31]['samples'][k][e+'_delay_ps']-by[1,0]['samples'][k][e+'_delay_ps'] for e in ('rise','fall')} for k in range(2)]
        good=all(r['hypothesis_point_checks_passed'] for r in by.values()) and all(v>0 for pulse in overlap for v in pulse.values())
        result.append(dict(variant=variant,hypothesis_feasible=bool(good),coarse_overlap_by_pulse=overlap,
                           zero_code_fast_quarter_headroom_ps=by[0,0]['zero_code_fast_quarter_headroom_ps'],
                           candidate_layout_qualified=False,bank_admitted=False,electrical_qualification_passed=False,qualified_phy=False))
    return result


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
                result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),source_failed=i['source_failed'],scope=SCOPE,qualified_phy=False))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=6,errors=sum(row['error'] is not None for row in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
