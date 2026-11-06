#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""All fifteen PVT conditions for both physically qualified counter repairs.

Consumes six complete passing SS/50% cases, then runs the remaining 84 cases.
Shared inter-component wires are still ideal; whole-clock/PHY stay unqualified.
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
import probe_counter_native_repairs_v183 as source
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
baseline=source.source.source.source
VERSION='native-repaired-counter-15pvt-duty40-50-60-v184.1'
CONTEXT='counter_native_repairs_pvt_v184'
SCOPE='Both physically qualified storage/setter component RC, 15 PVT x 40/50/60% duty x both stopped levels at 410MHz, fixed supplies; ideal shared inter-component wiring, no whole-clock RC, joint DCC first event, hardware warmup or PHY admission'
specifications=baseline.specifications


def fixture(out,spec,observations):
    first,rest=source.fixture(out,spec,observations).split('\n',1)
    if first!='OpenLVDS '+source.VERSION:raise ValueError('Native counter fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def assess(rows,matrix):
    if len(rows)!=90 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    actual=[json.dumps(r['task']['spec'],sort_keys=True) for r in rows];expected=[json.dumps(s,sort_keys=True) for s in matrix]
    if matrix!=specifications() or len(set(actual))!=90 or set(actual)!=set(expected):raise ValueError('Repaired counter PVT/duty/stopped-clock coverage changed')
    passed=all(r['result']['counter_feasibility_passed'] and math.isfinite(r['result']['minimum_clock_low_voltage_margin_v']) and r['result']['minimum_clock_low_voltage_margin_v']>=0 for r in rows)
    physical=all(r['result'].get('storage_component_physical_rc_qualified') is True and r['result'].get('setter_guard_geometry_qualified') is True for r in rows)
    return dict(component_pvt_screen_passed=bool(passed and physical),all_fifteen_pvt_conditions_present=True,
        storage_and_setter_component_rc_qualified=physical,whole_clock_rc_qualified=False,hardware_warmup_qualified=False,
        electrical_qualification_passed=False,qualified_phy=False)


def prepare(parent):
    m=source.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text());rows=r['rows']
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=6,errors=0,qualified_phy=False) or len(rows)!=6:
        raise ValueError('Require six complete native repaired-counter pilot cases')
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',parent/'cells.spice',parent/'pair.spice',ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json']
    for task,row in zip(m['tasks'],rows):
        folder=parent/task['id'];d=row['result']
        if (row!=json.loads((folder/'summary.json').read_text()) or row['task']!=task or row['error'] is not None
            or not d['hypothesis_point_checks_passed'] or not d['storage_component_physical_rc_qualified'] or not d['setter_guard_geometry_qualified']
            or any(sha(folder/n)!=h for n,h in row['files'].items())):raise ValueError('Require unchanged passing native pilot traces and both component geometries')
        current=baseline.measure(folder,task['spec'],i['devices'])
        if any(d.get(k)!=v for k,v in current.items() if k!='scope'):raise ValueError('Consumed native pilot does not reproduce')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    matrix=specifications();inherited=[t['spec'] for t in m['tasks']]
    if len(set(json.dumps(s,sort_keys=True) for s in inherited))!=6 or any(s not in matrix for s in inherited):raise ValueError('Pilot cases do not belong to the full PVT matrix')
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        specs=[s for s in matrix if s not in inherited],matrix=matrix,inherited_rows=rows,max_workers=2,scope=SCOPE)
    if len(identity['specs'])!=84:raise ValueError('Require all 84 remaining native PVT cases')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ('cells.spice','pair.spice'):write(out/name,(parent/name).read_text())
    tasks=[]
    for k,spec in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,i['devices']));tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ('cells.spice','pair.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['max_workers']!=2 or i['matrix']!=specifications()
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=84):raise ValueError('Repaired counter PVT context changed')
    origin=json.loads((ROOT/i['parent']/'summary.json').read_text())['rows']
    if origin!=i['inherited_rows'] or len(origin)!=6 or i['specs']!=[s for s in i['matrix'] if s not in [r['task']['spec'] for r in origin]]:
        raise ValueError('Consumed pilot or remaining PVT coverage changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,t['spec'],i['devices']):raise ValueError('Native PVT fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial native repaired-counter PVT')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();r=baseline.measure(folder,task['spec'],i['devices'])
                result=dict(r,storage_component_physical_rc_qualified=True,setter_guard_geometry_qualified=True,
                    whole_clock_rc_qualified=False,hardware_warmup_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=assess([*i['inherited_rows'],*rows],i['matrix']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=90,consumed_cases=6,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):run(out);print(out,flush=True)
