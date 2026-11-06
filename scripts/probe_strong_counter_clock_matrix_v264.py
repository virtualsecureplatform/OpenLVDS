#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend a passing actual shared-RC counter pilot to all PVT/clock conditions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import probe_fast_clear_counter_shared_rc_v269 as source
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
sha=source.sha
VERSION='strong-counter-shared-rc-15pvt-three-frequency-duty-matrix-v264.1'
CONTEXT='strong_counter_clock_matrix_v264'
SCOPE='Actual strong-storage counter and dual clock-driver shared RC, 15 PVT x 390/400/410MHz x 40/50/60% duty x both stopped levels, original 644-MOS native gates; no joint DCC, whole-clock, management warmup or PHY admission'
FLAGS=('held_before_request_passed','stopped_clock_clear_and_reassert_passed',
       'terminal_screen_passed','counter_feasibility_passed','phase_arming_passed',
       'stopped_clock_arm_clear_passed','alternating_phase_order_passed',
       'stopped_clock_intermediate_clear_passed','counter_shared_wire_rc_qualified')


def specifications():
    requirements=json.loads((ROOT/'requirements.json').read_text())
    duty=json.loads((ROOT/'clocking_duty_v2_2.json').read_text())['timing_overrides']['rx_reference_duty_range']
    if (requirements['clock_test_mhz']!=[390,400,410] or requirements['temperatures_c']!=[0,25,40]
        or set(requirements['process_corners'])!={'tt','ff','ss','fs','sf'} or duty!=[.4,.6]
        or requirements['supply_sweep'] is not False or requirements['digital_supply_v']!=1.8):
        raise ValueError('Counter matrix requires the fixed-supply approved PVT/frequency/duty contract')
    return [dict(s,mhz=f) for s in source.baseline.specifications() for f in (410,390,400)]


def point_passed(result):
    return (all(result.get(k) is True for k in FLAGS)
        and len(result.get('terminal_stress',[]))==source.NATIVE_MOS
        and all(s.get('passed') is True for s in result['terminal_stress'])
        and isinstance(result.get('minimum_clock_low_voltage_margin_v'),(int,float))
        and math.isfinite(result['minimum_clock_low_voltage_margin_v'])
        and result['minimum_clock_low_voltage_margin_v']>=0)


def assess(rows,matrix):
    if len(rows)!=270 or any(r.get('error') is not None or r.get('result') is None for r in rows):return None
    actual=[json.dumps(r['task']['spec'],sort_keys=True) for r in rows]
    expected=[json.dumps(s,sort_keys=True) for s in matrix]
    if matrix!=specifications() or len(set(actual))!=270 or set(actual)!=set(expected):
        raise ValueError('Require complete unique 270-case PVT/frequency/duty/stopped-level coverage')
    return dict(counter_clock_matrix_passed=all(point_passed(r['result']) for r in rows),
        complete_270_case_coverage=True,all_fifteen_pvt_conditions_present=True,
        counter_shared_wire_rc_retained=True,whole_clock_rc_qualified=False,
        hardware_warmup_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def fixture(out,spec,devices):
    first,rest=source.fixture(out,spec,devices).split('\n',1)
    if first!='OpenLVDS '+source.VERSION:raise ValueError('Original native counter stimulus changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def require_pilot(parent,m):
    state=json.loads((parent/'state.json').read_text());report=json.loads((parent/'summary.json').read_text())
    rows=report.get('rows') or []
    if (state!=dict(status='complete',cases=12,errors=0,qualified_phy=False) or len(rows)!=12
        or [r['task'] for r in rows]!=m['tasks'] or source.assess(rows)!=(report.get('comparison') or {})
        or not report['comparison'].get('actual_shared_counter_timing_pilot_passed')
        or any(not point_passed(r.get('result') or {}) for r in rows)):
        raise ValueError('Require all twelve complete passing actual shared-RC pilot cases')
    return rows


def prepare(parent):
    m=source.bound(parent);i=m['identity'];rows=require_pilot(parent,m)
    matrix=specifications();old=[r['task']['spec'] for r in rows]
    if len({json.dumps(s,sort_keys=True) for s in old})!=12 or any(s not in matrix for s in old):
        raise ValueError('Inherited pilot does not belong to the complete clock matrix')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json','cells.spice','pair.spice')]
    for row in rows:
        folder=parent/row['task']['id'];result=row['result']
        if (row!=json.loads((folder/'summary.json').read_text())
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
            or any(sha(folder/n)!=h for n,h in row['files'].items())):
            raise ValueError('Consumed complete native counter case changed')
        measured=source.baseline.measure(folder,row['task']['spec'],i['devices'])
        if any(result.get(k)!=v for k,v in measured.items() if k!='scope'):
            raise ValueError('Consumed original native counter metrics do not reproduce')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += [ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        matrix=matrix,specs=[s for s in matrix if s not in old],inherited_rows=rows,max_workers=2,priority=2,scope=SCOPE)
    if len(identity['specs'])!=258:raise ValueError('Require all 258 remaining native clock cases')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ('cells.spice','pair.spice'):(out/name).write_text((parent/name).read_text())
    tasks=[]
    for k,s in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,s,i['devices']))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ('cells.spice','pair.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['max_workers']!=2 or i['priority']!=2
        or i['matrix']!=specifications() or len(m['tasks'])!=258 or len(i['devices'])!=source.NATIVE_MOS
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items())):
        raise ValueError('Actual shared-counter full clock matrix context changed')
    origin=json.loads((ROOT/i['parent']/'summary.json').read_text())['rows']
    if (origin!=i['inherited_rows'] or len(origin)!=12 or any(not point_passed(r['result']) for r in origin)
        or i['specs']!=[s for s in i['matrix'] if s not in [r['task']['spec'] for r in origin]]):
        raise ValueError('Consumed pilot or remaining clock coverage changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,t['spec'],i['devices']):
            raise ValueError('Actual shared-counter clock fixture changed')
    return m


def measure(folder,i,s):
    return dict(source.baseline.measure(folder,s,i['devices']),counter_shared_wire_rc_qualified=True,
        whole_clock_rc_qualified=False,all_pvt_covered=False,hardware_warmup_qualified=False,
        electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial shared-counter clock matrix')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=assess([*i['inherited_rows'],*rows],i['matrix']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=270,consumed_cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
