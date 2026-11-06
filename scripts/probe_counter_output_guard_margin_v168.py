#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Target the measured low0 output/body stress without weakening native limits."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_static_phase_clock_drive_pvt_v156 as source
import counter_output_guards_v168 as guards
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
VERSION='counter-low0-output-guard-2-and-3um-ss-temperatures-v168.1'
CONTEXT='counter_output_guard_margin_v168'
SCOPE='Low0 output-guard sizing hypotheses on original component wire RC, SS0/SS25/SS40 50% duty both stopped levels, unchanged native timing and stress limits; new guard geometry and full clock assembly unqualified'


def variants(parent):
    cells=(parent/'cells.spice').read_text();module=(parent/'pair.spice').read_text()
    return {v:guards.libraries(cells,module,v) for v in ('2','3')}


def fixture(out,spec,devices):
    first,rest=source.fixture(out,spec,devices).split('\n',1)
    if first!='OpenLVDS '+source.VERSION:raise ValueError('Source fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def prepare(parent):
    m=source.bound(parent);i=m['identity'];rows=[]
    for index in (52,53,58,59,24,25):
        task=m['tasks'][index];folder=parent/str(index);row=json.loads((folder/'summary.json').read_text())
        if row['task']!=task or row['error'] is not None or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Completed failed source changed')
        result=source.measure(folder,task['spec'],i['devices'])
        if (row['result']!=result or result['terminal_screen_passed'] or result['counter_feasibility_passed']
            or task['spec']['process']!='ss' or task['spec']['temperature'] not in (0,25,40) or task['spec']['duty']!=.5
            or not all(result.get(k) is True for k in ('held_before_request_passed','stopped_clock_clear_and_reassert_passed','phase_arming_passed','stopped_clock_arm_clear_passed','alternating_phase_order_passed','stopped_clock_intermediate_clear_passed'))
            or result['minimum_clock_low_voltage_margin_v']<0):raise ValueError('Require actual SS0/SS25 50% terminal failures')
        rows.append(row)
    designs=variants(parent)
    for cells,module,_ in designs.values():
        original=source.original.original
        mapped=original.circuit.components.mapped_mos(cells+module,original.HARNESS,
            dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
        if mapped!=i['devices']:raise ValueError('Original native MOS observations changed')
    paths=[parent/'manifest.json',parent/'cells.spice',parent/'pair.spice']
    paths += [parent/r['task']['id']/n for r in rows for n in ['summary.json',*r['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    specs=[dict(variant=v,spec=row['task']['spec']) for v in designs for row in rows]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files=i['pdk_files'],simulator=provenance(),devices=i['devices'],specs=specs,
        proofs={v:d[2] for v,d in designs.items()},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    for v,(cells,module,_) in designs.items():
        directory=out/('guard_'+v);directory.mkdir();write(directory/'cells.spice',cells);write(directory/'pair.spice',module)
    for k,task in enumerate(specs):
        folder=out/str(k);folder.mkdir();write(folder/'bench.cir',fixture(out/('guard_'+task['variant']),task['spec'],i['devices']))
        tasks.append(dict(task,id=str(k),deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['max_workers']!=2):raise ValueError('Counter output-guard hypothesis changed')
    for v,(cells,module,proof) in variants(ROOT/i['parent']).items():
        if proof!=i['proofs'][v] or cells!=(out/('guard_'+v)/'cells.spice').read_text() or module!=(out/('guard_'+v)/'pair.spice').read_text():raise ValueError('Candidate native libraries changed')
    if len(m['tasks'])!=12 or len(i['specs'])!=12:raise ValueError('Require twelve complete SS-temperature stopped-level cases')
    for k,t in enumerate(m['tasks']):
        file=out/str(k)/'bench.cir'
        if t!=dict(i['specs'][k],id=str(k),deck_sha256=sha(file)) or file.read_text()!=fixture(out/('guard_'+t['variant']),t['spec'],i['devices']):raise ValueError('Native fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Preserve prior or partial counter hypotheses')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode()
                r=source.measure(folder,task['spec'],i['devices'])
                result=dict(r,hypothesis_point_checks_passed=r['counter_feasibility_passed'] and r['minimum_clock_low_voltage_margin_v']>=0,
                    candidate_layout_qualified=False,component_pvt_screen_passed=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):run(out);print(out,flush=True)
