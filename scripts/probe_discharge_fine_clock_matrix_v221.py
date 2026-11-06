#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full approved frequency/duty sparse-code screen of passing fine hypotheses.

Consume four exact pilot traces per admitted variant, run all 23 missing
combinations, and retain failures. This is component RC, never PHY admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_discharge_isolated_fine_bank_v220 as source
from probe_digital_dcc_v2 import atomic
from qualify_repaired_clock_counter_rc_v193 import sha
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=source.ROOT
VERSION='strong-discharge-fine-approved-frequency-duty-sparse-matrix-v221.1'
CONTEXT='discharge_fine_clock_matrix_v221'
SCOPE='Passing native component fine-stage hypotheses at all 390/400/410MHz x 40/50/60% duty x zero/fine31/first-coarse, SS40 only; no new common-wire RC, dense/update/all-PVT/clock-chain/PHY admission'


def admitted(summary):
    rows=summary['rows']
    if len(rows)!=8 or any(r.get('result') is None for r in rows):raise ValueError('Require every complete native fine-driver pilot result')
    comparison=source.compare(rows)
    if comparison is None or summary['comparison']!=comparison:raise ValueError('Require complete reproducible fine-driver pilot comparison')
    variants=[r['variant'] for r in comparison if r['component_hypothesis_passed'] is True]
    if not variants:raise ValueError('No passing fine-driver hypothesis; retain pilot and revise circuit')
    return variants


def specifications(variants):
    if not variants or variants!=[v for v in source.variants() if v in variants]:raise ValueError('Require unique admitted variants in original order')
    sample=source.specifications()[0]
    return [dict(sample,coarse=c,fine=f,frequency_mhz=mhz,duty=d,**v)
            for v in variants for c,f in ((0,0),(0,31),(1,0)) for mhz in (390,400,410) for d in (.4,.5,.6)]


def remaining(matrix,inherited):
    specs=[s for s in matrix if s not in [r['spec'] for r in inherited]]
    priority={(0,0,410,.6):0,(0,0,410,.4):1,(1,0,410,.6):2,(1,0,410,.4):3,(0,31,410,.5):4}
    return sorted(specs,key=lambda s:priority.get((s['coarse'],s['fine'],s['frequency_mhz'],s['duty']),5))


def fixture(out,i,s):
    text=source.fixture(ROOT/i['parent'],i,s);title='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original full native pulse fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def assess(rows,variants):
    matrix=specifications(variants)
    if len(rows)!=len(matrix) or any(r['error'] is not None or r['result'] is None for r in rows):return None
    actual=[json.dumps(r['spec'],sort_keys=True) for r in rows];expected=[json.dumps(s,sort_keys=True) for s in matrix]
    if len(set(actual))!=len(matrix) or set(actual)!=set(expected):raise ValueError('Complete frequency/duty/code coverage changed')
    results=[]
    for v in variants:
        selected=[r for r in rows if source.key(r['spec'])==source.key(v)]
        def delays(c,f,edge):return [x for r in selected if (r['spec']['coarse'],r['spec']['fine'])==(c,f) for x in r['result']['edge_delays_ps'][edge]]
        complete=all(len(r['result']['edge_delays_ps'][edge])==8 and all(source.math.isfinite(x) for x in r['result']['edge_delays_ps'][edge]) for r in selected for edge in ('rise','fall'))
        overlap={edge:min(delays(0,31,edge))-max(delays(1,0,edge)) if complete else None for edge in ('rise','fall')}
        passed=complete and all(r['result']['current_clock_interface_screen_passed'] for r in selected) and all(x>0 for x in overlap.values())
        results.append(dict(variant=v,complete_27_case_clock_stress_screen_passed=bool(passed),conservative_coarse_overlap_ps=overlap,
            frequency_duty_sparse_matrix_complete=True,new_common_routing_qualified=False,dense_legal_table_qualified=False,
            all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False))
    return results


def prepare(parent):
    m=source.bound(parent);i=m['identity'];state=json.loads((parent/'state.json').read_text());summary=json.loads((parent/'summary.json').read_text())
    if state!=dict(status='complete',cases=8,errors=0,qualified_phy=False):raise ValueError('Require complete unchanged fine-driver pilot')
    variants=admitted(summary);matrix=specifications(variants)
    inherited=[r for r in summary['rows'] if {k:r['spec'][k] for k in ('driver','fine_copies')} in variants]
    paths=[parent/n for n in ('manifest.json','summary.json','state.json')]+[parent/name/'bank.spice' for name in m['libraries']]
    for task,row in zip(m['tasks'],summary['rows']):
        folder=parent/task['id']
        if row!=json.loads((folder/'summary.json').read_text()) or row['task']!=task or row['spec']!=task['spec'] or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Pilot native trace changed')
        if row in inherited and source.measure(folder,i,task['spec'])!=row['result']:raise ValueError('Consumed native pilot metrics do not reproduce')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    if len(inherited)!=4*len(variants):raise ValueError('Require four consumed traces for every admitted variant')
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),variants=variants,matrix=matrix,
                  specs=remaining(matrix,inherited),inherited_rows=inherited,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False);tasks=[]
    for k,s in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,identity,s));tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];matrix=specifications(i['variants'])
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['matrix']!=matrix or i['max_workers']!=2 or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())):raise ValueError('Full sparse clock matrix context changed')
    summary=json.loads((ROOT/i['parent']/'summary.json').read_text())
    if admitted(summary)!=i['variants'] or i['inherited_rows']!=[r for r in summary['rows'] if source.key(r['spec']) in {source.key(v) for v in i['variants']}]:raise ValueError('Admitted pilot variants changed')
    if i['specs']!=remaining(matrix,i['inherited_rows']) or len(m['tasks'])!=23*len(i['variants']):raise ValueError('Remaining frequency/duty coverage changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,i,t['spec']):raise ValueError('Full sparse clock fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial full sparse clock screen')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];r=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();r=source.measure(folder,i,task['spec']);r.update(scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=r,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=assess([*i['inherited_rows'],*rows],i['variants']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=len(i['matrix']),consumed_cases=len(i['inherited_rows']),errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
