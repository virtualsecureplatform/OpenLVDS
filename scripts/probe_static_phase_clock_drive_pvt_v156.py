#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""All-PVT component-clock-drive screen with unchanged complete native RC.

Consumes four independently verified SS40 endpoints; shared inter-driver wires
remain ideal. Full clock-island RC, joint DCC events, warmup and PHY stay open.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_static_phase_clock_drive_v2 as original
import verify_static_phase_clock_drive_v2 as proof
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=original.ROOT
VERSION='native-two-buffer-phase-counter-15pvt-duty40-50-60-v156.1'
CONTEXT='static_phase_clock_drive_pvt_v156'
SCOPE='Native component-RC two-buffer phase counter, 15 PVT and 40/50/60% duty at 410 MHz; ideal shared inter-driver wires, no whole-clock RC, joint DCC events, hardware warmup, electrical or PHY admission'
def specifications():
    r=json.loads((ROOT/'requirements.json').read_text())
    points=[(p,t) for p in r['process_corners'] for t in r['temperatures_c']]
    priority=[('ff',0),('fs',40),('sf',40),('tt',25),('ss',40)]
    points=[p for p in priority if p in points]+[p for p in points if p not in priority]
    base=original.specifications()[0]
    return [dict(base,process=p,temperature=t,duty=d,stop_level=level)
            for p,t in points for d in (.4,.5,.6) for level in (0,1)]


def fixture(out,spec,devices):
    deck=original.fixture(out,spec,devices);first,rest=deck.split('\n',1)
    if first!='OpenLVDS '+original.VERSION:raise ValueError('Baseline clock-drive fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def measure(folder,spec,devices):
    return dict(original.measure(folder,spec,devices),scope=SCOPE)


def assess(rows,matrix):
    if len(rows)!=len(matrix) or any(r['error'] is not None or r['result'] is None for r in rows):return None
    actual=[json.dumps(r['task']['spec'],sort_keys=True) for r in rows]
    expected=[json.dumps(s,sort_keys=True) for s in matrix]
    if matrix!=specifications() or len(set(actual))!=90 or set(actual)!=set(expected):raise ValueError('Clock-drive PVT/duty coverage changed')
    native=all(r['result']['counter_feasibility_passed'] for r in rows)
    low=all(np.isfinite(r['result']['minimum_clock_low_voltage_margin_v']) and r['result']['minimum_clock_low_voltage_margin_v']>=0 for r in rows)
    return dict(component_pvt_screen_passed=bool(native and low),all_fifteen_pvt_conditions_present=True,
                all_clock_low_phase_margins_passed=low,whole_clock_rc_qualified=False,hardware_warmup_qualified=False,
                electrical_qualification_passed=False,qualified_phy=False)


def prepare(receipt):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice engine')
    report=json.loads((receipt/'summary.json').read_text());ri=report['identity']
    if (receipt.parent!=ROOT/'build/diagnostics'/proof.CONTEXT or ri['version']!=proof.VERSION
        or receipt.name!=hashlib.sha256(json.dumps(ri,sort_keys=True).encode()).hexdigest()[:16]
        or not report['all_declared_raw_waveforms_verified'] or not report['all_profiles_passed']
        or any(sha(ROOT/n)!=h for n,h in ri['inputs'].items())):
        raise ValueError('Require complete independently passing two-buffer native source')
    parent=ROOT/ri['parent'];m=original.bound(parent);proof.regenerate(parent,m)
    aggregate=json.loads((parent/'summary.json').read_text())['rows']
    if json.loads((parent/'state.json').read_text())!=dict(status='clock_drive_pilot_complete',cases=4,errors=0,qualified_phy=False) or len(aggregate)!=4:
        raise ValueError('Require four complete source cases')
    inherited=[]
    for task,row in zip(m['tasks'],aggregate):
        folder=parent/task['id']
        if (row!=json.loads((folder/'summary.json').read_text()) or row['task']!=task or row['error'] is not None
            or not proof.REQUIRED<=set(row['files']) or any(sha(folder/n)!=h for n,h in row['files'].items())
            or original.measure(folder,task['spec'],m['identity']['devices'])!=row['result'] or not row['result']['counter_feasibility_passed']
            or not np.isfinite(row['result']['minimum_clock_low_voltage_margin_v']) or row['result']['minimum_clock_low_voltage_margin_v']<0):
            raise ValueError('Consumed complete native source trace changed')
        inherited.append(row)
    cells=(parent/'cells.spice').read_text();module=(parent/'pair.spice').read_text()
    paths=[receipt/'summary.json',parent/'manifest.json',parent/'state.json',parent/'summary.json',ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json']
    paths += [ROOT/n for n in ri['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    matrix=specifications();old_specs=[r['task']['spec'] for r in inherited]
    if len(old_specs)!=4 or any(s not in matrix for s in old_specs):raise ValueError('Source cases do not belong to PVT matrix')
    identity=dict(m['identity'],version=VERSION,parent=str(parent.relative_to(ROOT)),source_receipt=str(receipt.relative_to(ROOT)),
        inputs={**m['identity']['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        matrix=matrix,specs=[s for s in matrix if s not in old_specs],inherited_rows=inherited,max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells);write(out/'pair.spice',module);tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,identity['devices']))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ['cells.spice','pair.spice']},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['matrix']!=specifications() or i['max_workers']!=2
        or i['specs']!=[s for s in i['matrix'] if s not in [r['task']['spec'] for r in i['inherited_rows']]]
        or i['clock_drivers']!=2 or not i['original_native_devices_preserved']
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=86):raise ValueError('Native clock-drive context changed')
    source=json.loads((ROOT/i['parent']/'summary.json').read_text())
    if source['rows']!=i['inherited_rows'] or len(i['inherited_rows'])!=4:raise ValueError('Consumed source rows changed')
    for n,task in enumerate(m['tasks']):
        if (task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']
            or (out/str(n)/'bench.cir').read_text()!=fixture(out,task['spec'],i['devices'])):raise ValueError('Native clock-drive deck/task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native clock-drive experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=m['identity']['inherited_rows'],comparison=assess([*m['identity']['inherited_rows'],*rows],m['identity']['matrix']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='clock_drive_pvt_complete',cases=90,consumed_cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:run(out);print(out,flush=True)
