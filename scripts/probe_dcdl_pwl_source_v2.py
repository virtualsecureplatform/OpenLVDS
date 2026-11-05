#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full-duration native DCDL source-representation convergence isolation.

Use a bounded voltage-PWL approximation of the original tanh input. Retain the
same native circuits, tolerances, saved terminals and complete 20 ns experiment.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import probe_dcdl_mux_return_v2 as baseline
import diagnose_dcdl_iterations_v2 as failure
import tanh_voltage_pwl_v2 as source
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=baseline.ROOT
VERSION='native-dcdl-bounded-voltage-pwl-source-isolation-v2.1'
CONTEXT='dcdl_pwl_source_v2'


def fixture(out,spec,devices):
    text=baseline.fixture(out,spec,devices);first,rest=text.split('\n',1)
    if first!='OpenLVDS '+baseline.VERSION:raise ValueError('Original native fixture changed')
    matches=re.findall(r'(?m)^BIN IN 0 V=\{[^\n]+\}$',rest)
    if len(matches)!=1:raise ValueError('Require exactly the retained behavioral tanh source')
    points,certificate=source.samples(spec['input_slew_ps'])
    return 'OpenLVDS '+VERSION+'\n'+rest.replace(matches[0],source.statement(points),1),certificate


def checked_baseline(case):
    parent=case.parent;m=baseline.bound(parent);task=m['tasks'][int(case.name)]
    r=json.loads((case/'summary.json').read_text())
    if (task['id']!=case.name or r['task']!=task or r['error'] is None or r['result'] is not None
        or (case/'bench.cir').read_text()!=baseline.fixture(parent,task['spec'],m['identity']['devices'])
        or any(sha(case/n)!=h for n,h in r['files'].items())):raise ValueError('Require the unchanged terminal native baseline failure')
    log=failure.failure((case/'ngspice.log').read_text())
    if log['reported_time_s']>=20e-9:raise ValueError('Require an incomplete baseline transient')
    return m,task,r


def prepare(case):
    if engine()!='ngspice':raise ValueError('Use the pinned native ngspice engine')
    m,task,r=checked_baseline(case);i=m['identity'];parent=case.parent
    cells,bank,orders,devices,paths=baseline.libraries(ROOT/i['compound'],ROOT/i['fine'],Path(i['source_library']))
    if (cells!=(parent/'cells.spice').read_text() or bank!=(parent/'bank.spice').read_text()
        or orders!=i['orders'] or devices!=i['devices']):raise ValueError('Original native libraries or MOS coverage changed')
    _,certificate=fixture(parent,task['spec'],devices)
    paths += [parent/'manifest.json',case/'summary.json',*[case/n for n in r['files']],*[ROOT/n for n in i['inputs']]]
    paths += [Path(__file__),Path(source.__file__),Path(baseline.__file__),Path(failure.__file__),ROOT/'scripts/run_native_binary_v2.py',
              ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    identity=dict(version=VERSION,baseline_case=str(case.relative_to(ROOT)),spec=task['spec'],devices=devices,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=i['pdk_files'],simulator=provenance(),
        source_certificate=certificate,maximum_step_ps=2,stop_ns=20,max_workers=1,
        scope='Source-representation isolation only; no native hardware change, timing-table, full-PVT or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells);write(out/'bank.spice',bank)
    text,cert=fixture(out,task['spec'],devices)
    if cert!=certificate:raise ValueError('Source representation certificate changed')
    write(out/'bench.cir',text)
    atomic(out/'manifest.json',dict(identity=identity,libraries={n:sha(out/n) for n in ['cells.spice','bank.spice']},deck_sha256=sha(out/'bench.cir'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];text,certificate=fixture(out,i['spec'],i['devices'])
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or engine()!='ngspice' or any(sha(out/n)!=h for n,h in m['libraries'].items())
        or sha(out/'bench.cir')!=m['deck_sha256'] or (out/'bench.cir').read_text()!=text or certificate!=i['source_certificate']
        or i['stop_ns']!=20 or i['maximum_step_ps']!=2 or i['max_workers']!=1):raise ValueError('Native PWL source isolation context changed')
    return m


def measure(out,spec,devices):
    names,w=validate(out/'bench.raw',{'v(in)'},20e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;vin=w[:,idx['v(in)']]
    expected=np.array([source.waveform(float(v),spec['input_slew_ps']) for v in t])
    deviation=float(np.max(np.abs(vin-expected)));_,certificate=source.samples(spec['input_slew_ps'])
    if deviation>certificate['maximum_interpolation_bound_v']+1e-8:raise ValueError('Actual input exceeds the certified representation error')
    levels={}
    for rising,label in [(True,'rise'),(False,'fall')]:
        edges={v:crossings(t,vin+(.9-v),rising) for v in [.18,.9,1.62]}
        if any(len(v)!=2 for v in edges.values()):raise ValueError('Actual PWL source pulse count changed')
        slews=(edges[1.62]-edges[.18]) if rising else (edges[.18]-edges[1.62])
        if np.max(np.abs(slews-spec['input_slew_ps']))>.02:raise ValueError('Actual PWL source 10--90% slew changed')
        targets=source.CENTERS_PS[::2] if rising else source.CENTERS_PS[1::2]
        if np.max(np.abs(edges[.9]-targets))>.02:raise ValueError('Actual PWL source midpoint epoch changed')
        levels[label]=dict(midpoint_ps=edges[.9].tolist(),slew_10_90_ps=slews.tolist())
    native=error=None
    try:native=baseline.measure(out,spec,devices)
    except ValueError as e:error=str(e)
    return dict(numerically_completed=True,actual_source_representation_passed=True,maximum_input_difference_v=deviation,
        input_edges=levels,native_result=native,native_measurement_error=error,qualified_phy=False,legal_code_table_admitted=False,
        scope='Full-duration bounded-PWL input experiment through unchanged native legacy return-mux bank; no equivalence/speedup claim to its aborted baseline and no ROM, all-PVT or PHY admission')


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native source-isolation run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));result=error=wall=None
        try:
            with lease(ROOT,priority=0,label=CONTEXT):
                bound(out);start=time.monotonic()
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(out/'ngspice.log'),str(out/'bench.cir')],capture_output=True,text=True)
                wall=time.monotonic()-start
            write(out/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(out,i['spec'],i['devices'])
        except Exception as e:error=str(e)
        bound(out)
        files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['.execution.lock','manifest.json','state.json']}
        atomic(out/'summary.json',dict(result=result,error=error,solver_wall_seconds=wall,files=files,qualified_phy=False))
        atomic(out/'state.json',dict(status='pwl_source_isolation_complete',numerically_completed=result is not None,qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    else:run(out)
