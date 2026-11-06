#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend passing routed regular-pair clock transport to all fifteen PVT points."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import probe_regular_regenerated_joint_periodic_v288 as source
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from run_regular_regenerated_physical_v284 import NATIVE_FLAGS

ROOT=source.ROOT
sha=source.sha
VERSION='actual-regular-pair-routed-sparse-clock-15pvt-matrix-v291.1'
CONTEXT='regular_regenerated_pvt_v291'
SCOPE='405 actual routed regular-pair sparse-code clock cases across 15 PVT and 390/400/410 MHz, 40/50/60% duty; dense/common tables, updates, joint DCC/full-clock and PHY remain unqualified'


def specifications():
    req=json.loads((ROOT/'requirements.json').read_text())
    duty=json.loads((ROOT/'clocking_duty_v2_2.json').read_text())['timing_overrides']['rx_reference_duty_range']
    if (req['clock_test_mhz']!=[390,400,410] or req['temperatures_c']!=[0,25,40]
        or set(req['process_corners'])!={'tt','ff','ss','fs','sf'} or duty!=[.4,.6]
        or req['supply_sweep'] is not False or req['digital_supply_v']!=1.8 or req['analog_supply_v']!=3.3):
        raise ValueError('Require approved fixed-supply PVT and clock contract')
    return [s for process in req['process_corners'] for temperature in req['temperatures_c']
        for s in source.specifications(dict(source.native.spec(),process=process,temperature=temperature))]


def point_passed(r):
    return (all(r.get(k) is True for k in NATIVE_FLAGS) and r.get('whole_bank_rc_retained') is True
        and len(r.get('terminal_stress',[]))==1529 and all(d.get('passed') is True for d in r['terminal_stress'])
        and len(r.get('programming_gates',[]))==173 and all(d.get('passed') is True for d in r['programming_gates'])
        and bool(r.get('controls')) and all(d.get('passed') is True for d in r['controls'])
        and all(len(r.get('edge_delays_ps',{}).get(edge,[]))==8
            and all(math.isfinite(v) and v>0 for v in r['edge_delays_ps'][edge]) for edge in ('rise','fall')))


def assess(rows,matrix):
    if len(rows)!=405 or any(r.get('error') is not None or r.get('result') is None for r in rows):return None
    actual=[json.dumps(r['spec'],sort_keys=True) for r in rows]
    if matrix!=specifications() or len(set(actual))!=405 or set(actual)!={json.dumps(s,sort_keys=True) for s in matrix}:
        raise ValueError('Require all 405 unique approved PVT/code/frequency/duty conditions')
    groups=[]
    for process in ('tt','ff','ss','fs','sf'):
        for temperature in (0,25,40):
            selected=[r for r in rows if (r['spec']['process'],r['spec']['temperature'])==(process,temperature)]
            histories=all(point_passed(r['result']) for r in selected)
            by={code:[r['result'] for r in selected if (r['spec']['coarse'],r['spec']['fine'])==code] for code in ((0,0),(0,31),(1,0))}
            overlap={edge:min(v for r in by[0,31] for v in r['edge_delays_ps'][edge])-max(v for r in by[1,0] for v in r['edge_delays_ps'][edge]) if histories else None for edge in ('rise','fall')}
            progression=histories and all(min(v for r in by[code] for v in r['edge_delays_ps'][edge])>max(v for r in by[0,0] for v in r['edge_delays_ps'][edge]) for code in ((0,31),(1,0)) for edge in ('rise','fall'))
            groups.append(dict(process=process,temperature=temperature,cases=len(selected),all_native_points_passed=histories,
                conservative_coarse_overlap_ps=overlap,positive_progress_from_zero=bool(progression),
                sparse_clock_pvt_point_passed=bool(histories and progression and all(v is not None and math.isfinite(v) and v>0 for v in overlap.values()))))
    return dict(complete_405_case_coverage=True,all_fifteen_pvt_conditions_present=True,pvt_points=groups,
        sparse_clock_pvt_matrix_passed=all(g['sparse_clock_pvt_point_passed'] for g in groups),
        actual_joint_rc_retained=all(r['result'].get('whole_bank_rc_retained') is True for r in rows),
        dense_common_tables_qualified=False,updates_qualified=False,corrected_dcc_output_qualified=False,
        whole_clock_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def fixture(out,i,s):
    text=source.fixture(out,i,s);title='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed periodic fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def require_pilot(parent,m):
    r=json.loads((parent/'summary.json').read_text());rows=r.get('rows') or []
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=27,errors=0,qualified_phy=False)
        or len(rows)!=27 or [row['task'] for row in rows]!=m['tasks']
        or [row['spec'] for row in rows]!=m['identity']['specs']
        or r.get('comparison')!=source.compare(rows,m['identity']['specs'])
        or (r.get('comparison') or {}).get('all_current_clock_interface_cases_passed') is not True
        or any(not point_passed(row.get('result') or {}) for row in rows)):
        raise ValueError('Require complete passing 27-case actual routed native clock screen')
    return rows


def prepare(parent):
    m=source.bound(parent);i=m['identity'];rows=require_pilot(parent,m);matrix=specifications()
    old=[r['spec'] for r in rows]
    if len({json.dumps(s,sort_keys=True) for s in old})!=27 or any(s not in matrix for s in old):raise ValueError('Inherited clock pilot coverage changed')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')]
    for row in rows:
        case=parent/row['task']['id']
        if (row!=json.loads((case/'summary.json').read_text())
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
            or any(sha(case/n)!=h for n,h in row['files'].items())
            or source.measure(case,dict(i,spec=row['spec']))!=row['result']):
            raise ValueError('Consumed complete routed clock trace does not reproduce')
        paths += [case/'summary.json',*[case/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += [ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),matrix=matrix,specs=[s for s in matrix if s not in old],
        inherited_rows=rows,inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},max_workers=2,priority=2,scope=SCOPE)
    if len(identity['specs'])!=378:raise ValueError('Require 378 new conditions after consuming the 27-case screen')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for k,s in enumerate(identity['specs']):
        case=out/str(k);case.mkdir();(case/'bench.cir').write_text(fixture(out,identity,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(case/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];origin=i['inherited_rows']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or source.zero.engine()!='ngspice' or source.zero.provenance()!=i['simulator'] or i['max_workers']!=2 or i['priority']!=2
        or i['matrix']!=specifications() or len(m['tasks'])!=378 or len(i['observations']['devices'])!=1529
        or sha(Path(source.native.CAD))!=i['cad']['sha256']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['parent']/'bank.spice')!=m['bank_sha256']
        or origin!=json.loads((ROOT/i['parent']/'summary.json').read_text())['rows']
        or len(origin)!=27 or any(not point_passed(r['result']) for r in origin)
        or i['specs']!=[s for s in i['matrix'] if s not in [r['spec'] for r in origin]]):
        raise ValueError('Actual routed regular-pair PVT matrix context changed')
    for k,t in enumerate(m['tasks']):
        path=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(path)) or path.read_text()!=fixture(out,i,t['spec']):raise ValueError('Actual routed PVT fixture changed')
    return m


def measure(case,i,s):return dict(source.measure(case,dict(i,spec=s)),scope=SCOPE)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial routed PVT campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            case=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(case/'ngspice.log'),str(case/'bench.cir')],capture_output=True,text=True)
                (case/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(case,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in case.iterdir() if p.is_file()});atomic(case/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=assess([*i['inherited_rows'],*rows],i['matrix']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=405,consumed_cases=27,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
