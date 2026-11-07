#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the unchanged passing 5x5 output shunt across original counter boundaries.

Reuse the verified SS0/40%-duty stopped-low trace; simulate the other eleven
points. Component RC and ideal shared wires do not qualify a routed counter.
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
import probe_request_taper_output_shunt_v332 as source
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
VERSION='unchanged-5x5-output-shunt-counter-duty-temperature-stop-boundaries-v334.1'
CONTEXT='large_shunt_counter_boundaries_v334'
sha=source.sha
atomic=source.atomic
SCOPE=('Unchanged passing 808-MOS/57-MIM 5x5 output-shunt counter at SS0/SS40 '
       '410MHz 40/50/60% duty and both stopped levels; one retained verified '
       '26ns trace plus eleven new native points; component RC/ideal new shared '
       'wires only, no new geometry/shared RC/other clock/PVT/DCC/PHY admission')


def specifications():
    base=source.specification()
    return [dict(base,temperature=t,duty=d,stop_level=level)
            for t in (0,40) for d in (.4,.5,.6) for level in (0,1)]


def fixture(out,spec,devices):
    text=source.fixture(out,spec,devices)
    old='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(old):raise ValueError('Original full counter fixture changed')
    return text.replace(old,'OpenLVDS '+VERSION+'\n',1)


def task_plan(out,original,devices):
    rows=[]
    for k,spec in enumerate(specifications()):
        if k==0:
            rows.append(dict(id='0',spec=spec,mode='retained',source_case=str(original.relative_to(ROOT)),
                             deck_sha256=sha(original/'bench.cir')))
        else:
            rows.append(dict(id=str(k),spec=spec,mode='simulate',
                             deck_sha256=hashlib.sha256(fixture(out,spec,devices).encode()).hexdigest()))
    return rows


def require_baseline(parent,evidence):
    m=source.bound(parent);i=m['identity'];case=parent/'0'
    row=json.loads((case/'summary.json').read_text())
    report=json.loads((evidence/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
            or json.loads((parent/'summary.json').read_text()).get('boundary_point_passed') is not True
            or row['task']!=m['tasks'][0] or row['task']['spec']!=specifications()[0]
            or row['error'] is not None or row['result'] is None
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('parameters_changed') is not False or len(report.get('rows',[]))!=1
            or report['rows'][0]['case']!=str(case.relative_to(ROOT))
            or report['rows'][0].get('all_original_native_metrics_reproduced') is not True
            or report['rows'][0].get('native_mos')!=808
            or any(sha(ROOT/n)!=h for n,h in report['inputs'].items())
            or any(sha(case/n)!=h for n,h in row['files'].items())):
        raise ValueError('Require naturally terminal, fully replayed passing 5x5 native source')
    measured=dict(source.candidate.measure(case,i,i['spec']),scope=source.SCOPE)
    if measured!=row['result'] or not point_passed(measured):
        raise ValueError('Original complete passing native source no longer reproduces')
    sample=report['rows'][0]['exact_limiting_samples']['whole_counter']
    worst=max(measured['terminal_stress'],key=lambda d:d['max_terminal_difference_v'])
    if sample['device']!=worst['device'] or sample['peak_v']!=worst['max_terminal_difference_v'] or sample['margin_v']<=0:
        raise ValueError('Exact limiting native stress sample changed')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*m['libraries'])]
    paths += [case/'summary.json',*[case/n for n in row['files']],evidence/'summary.json']
    paths += [ROOT/n for n in {*i['inputs'],*report['inputs']}]
    return m,row,paths


def prepare(parent,evidence):
    m,baseline,paths=require_baseline(parent,evidence);i=m['identity']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),evidence=str(evidence.relative_to(ROOT)),
        specs=specifications(),devices=i['devices'],inputs=inputs,guards=source.candidate.guard_inputs(inputs),
        simulator=i['simulator'],pdk_files=i['pdk_files'],external_files=i['external_files'],
        library_sha256=m['libraries'],retained_result_sha256=hashlib.sha256(json.dumps(baseline['result'],sort_keys=True).encode()).hexdigest(),
        max_workers=2,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in m['libraries']:(out/n).write_bytes((parent/n).read_bytes())
    devices=i['devices'][source.candidate.VARIANT]
    tasks=task_plan(out,parent/'0',devices)
    for task in tasks:
        folder=out/task['id'];folder.mkdir()
        if task['mode']=='simulate':(folder/'bench.cir').write_text(fixture(out,task['spec'],devices))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries=m['libraries'],qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or i['scope']!=SCOPE or (i['max_workers'],i['priority'])!=(2,1)
            or i['guards']!=source.candidate.guard_inputs(i['inputs']) or m['libraries']!=i['library_sha256']
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items())
            or engine()!='ngspice' or provenance()!=i['simulator']):
        raise ValueError('Unchanged 5x5 counter boundary campaign changed')
    devices=source.candidate.source.observations((out/'cells.spice').read_text(),(out/'pair.spice').read_text())
    if devices!=i['devices'][source.candidate.VARIANT] or len(devices)!=808:
        raise ValueError('Original native counter terminal map changed')
    if m['tasks']!=task_plan(out,ROOT/i['parent']/'0',devices):raise ValueError('Require one retained plus eleven new original boundary points')
    for task in m['tasks'][1:]:
        deck=out/task['id']/'bench.cir'
        if sha(deck)!=task['deck_sha256'] or deck.read_text()!=fixture(out,task['spec'],devices):
            raise ValueError('Original full 26ns boundary fixture changed')
    return m


def point_passed(result):
    if not result:return False
    keys=('hypothesis_point_checks_passed','counter_feasibility_passed','terminal_screen_passed',
          'held_before_request_passed','stopped_clock_clear_and_reassert_passed','phase_arming_passed',
          'stopped_clock_arm_clear_passed','alternating_phase_order_passed','stopped_clock_intermediate_clear_passed')
    stress=result.get('terminal_stress',[]);windows=result.get('low_windows',{})
    margin=result.get('minimum_clock_low_voltage_margin_v',float('nan'))
    remaining=windows.get('minimum_remaining_low_window_ps',float('nan'))
    return bool(all(result.get(k) is True for k in keys) and len(stress)==808
        and all(d['passed'] and math.isfinite(d['max_terminal_difference_v'])
                and d['max_terminal_difference_v']<=d['limit_v'] for d in stress)
        and windows.get('all_three_assertions_in_original_low_windows') is True
        and math.isfinite(margin) and margin>=0 and math.isfinite(remaining) and remaining>0)


def assess(rows):
    if len(rows)!=12 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['task']['spec'] for r in rows]!=specifications():raise ValueError('Require exact original duty/temperature/stop coverage')
    return dict(all_twelve_native_points_present=True,retained_native_points=1,new_native_points=11,
        component_hypothesis_passed=all(point_passed(r['result']) for r in rows),
        counter_shared_wire_rc_qualified=False,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial boundary campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                if task['mode']=='retained':
                    original=ROOT/task['source_case'];old=json.loads((original/'summary.json').read_text())
                    old_i=json.loads((parent/'manifest.json').read_text())['identity']
                    reproduced=dict(source.candidate.measure(original,old_i,task['spec']),scope=source.SCOPE)
                    if (old['error'] is not None or reproduced!=old['result'] or not point_passed(reproduced)
                            or hashlib.sha256(json.dumps(reproduced,sort_keys=True).encode()).hexdigest()!=i['retained_result_sha256']):
                        raise ValueError('Retained passing native point changed')
                    atomic(folder/'retained_case.json',dict(source_case=task['source_case'],
                        original_summary_sha256=sha(original/'summary.json'),original_files=old['files'],
                        all_original_native_metrics_reproduced=True))
                    result=dict(reproduced,scope=SCOPE)
                else:
                    with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                        bound(out,full=False)
                        p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                    result=dict(source.candidate.measure(folder,i,task['spec']),scope=SCOPE)
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=assess(rows),qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('parent',type=Path);q.add_argument('evidence',type=Path)
    q=sub.add_parser('run');q.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.parent.resolve(),a.evidence.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
