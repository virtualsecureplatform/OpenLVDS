#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Both-polarity source waveform checks at all fifteen fixed-supply PVT points."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import probe_driver_output_shape as shape
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,engine,provenance

ROOT=Path(__file__).resolve().parents[1]
sha=shape.sha


def cases(req):
    result=[dict(id=f'{p}_{t}_{op}',process=p,temperature=t,op=op) for p,t,op in itertools.product(req['process_corners'],req['temperatures_c'],shape.CASES)]
    if len(result)!=30 or len({r['id'] for r in result})!=30:raise ValueError('Require all fifteen distinct PVT points and both polarities')
    return result


def pair_checks(rows,waveforms,req):
    if len(rows)!=2 or [r['task'] for r in rows]!=shape.CASES or set(waveforms)!=set(shape.CASES):return False
    return bool(all(r['returncode']==0 and r['metrics'] is not None and
        req['tx_differential_min_v']<=abs(r['initial_dc']['differential_v'])<=req['tx_differential_max_v'] and
        req['tx_common_mode_min_v']<=r['initial_dc']['common_mode_v']<=req['tx_common_mode_max_v'] and
        max(r['initial_dc'][n] for n in ['differential_pp_v','common_mode_pp_v'])<=1e-4 and
        r['metrics']['common_mode_pp_v']<=.150 and r['metrics']['rising_output_edges']==22 for r in rows) and
        all(v['within_reference'] for v in waveforms.values()))


def pilot_ready(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/driver_output_shape'):raise ValueError('Use the completed two-polarity shaping pilot')
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];stamp=sha(parent/'manifest.json')
    if parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or provenance()!=i['simulator']:raise ValueError('Shaping identity/runtime changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Shaping input/producer changed')
    # An admission check never runs a missing producer or retries partial data.
    if not (parent/'summary.json').exists() or any(not (parent/c/'summary.json').exists() for c in shape.CASES):raise ValueError('Complete both shaping polarities before source PVT')
    r=json.loads((parent/'summary.json').read_text())
    if r.get('diagnostic_complete') is not True or r.get('source_pilot_reference_checks_passed') is not True or r.get('manifest_sha256')!=stamp:raise ValueError('Both-polarity nominal pilot must pass')
    paths=[parent/'manifest.json',parent/'summary.json'];results=[]
    if [t['id'] for t in m['tasks']]!=shape.CASES:raise ValueError('Pilot polarity coverage changed')
    for task in m['tasks']:
        folder=parent/task['id'];row=json.loads((folder/'summary.json').read_text())
        if row.get('returncode')!=0 or row.get('manifest_sha256')!=stamp or any(sha(folder/n)!=h for n,h in dict(task['files'],**row['files']).items()):raise ValueError('Completed pilot fixture/output changed')
        wave,headers=shape.read_wave(folder/'bench.cir.prn')
        if shape.pilot.measure(folder,'taper_16_32_64')!=row['metrics'] or shape.initial_dc(wave,headers)!=row['initial_dc']:raise ValueError('Completed pilot remeasurement changed')
        results.append(row);paths += [folder/n for n in set(task['files'])|set(row['files'])|{'summary.json'}]
    low,high=[row['initial_dc']['differential_v'] for row in results]
    measured={op:shape.transitions(*shape.read_wave(parent/op/'bench.cir.prn'),low,high) for op in shape.CASES}
    req=json.loads((ROOT/'requirements.json').read_text())
    if results!=r['results'] or measured!=r['calibrated_transitions'] or not pair_checks(results,measured,req):raise ValueError('Nominal shaping reference checks changed')
    return m,paths


def fixture(deck,old,new,task):
    include=f'.include "{old}/source.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 80n 0 1p']:raise ValueError('Require original shaping fixture')
    for line in ['VIO VDDIO 0 3.3','VDIG VDDD 0 1.8','VREF VREF 0 1.2','IREF IREF 0 35u','RT P N 100','CP P 0 2p','CN N 0 2p']:
        if deck.splitlines().count(line)!=1:raise ValueError('Fixed supply, bias or load changed')
    rows=re.findall(r'(?m)^\.lib "[^"\n]+" tt$',deck)
    if len(rows)!=1 or deck.splitlines().count('.options device temp=25')!=1:raise ValueError('Require original TT25 seed')
    return deck.replace(include,f'.include "{new}/source.spice"').replace(rows[0],rows[0][:-2]+task['process']).replace('.options device temp=25','.options device temp='+str(task['temperature']))


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Use pinned ngspice')
    m,paths=pilot_ready(parent);previous=m['identity'];req=json.loads((ROOT/'requirements.json').read_text());tasks=cases(req)
    source=(parent/'negative_op/source.spice').read_text()
    if source!=(parent/'positive_op/source.spice').read_text():raise ValueError('Nominal polarities use different circuits')
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={**previous['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths},'requirements.json':sha(ROOT/'requirements.json')},
        code={**previous['code'],'qualify_driver_output_shape_source.py':sha(Path(__file__))},simulator=provenance(),
        scope='Thirty source cases: all five processes x 0/25/40 C x two initial logic polarities. Unchanged shaped circuit, 80 ns/1 ps, fixed supplies/reference, 100 ohm/2 pF per pin load, 800 Mb/s. Fresh DC calibration per PVT, waveform reference checks, actual supply currents and added-MOS voltages. Source waveform matrix only; no complete generator certification, physical/native selection, current/stress admission or PHY release.')
    out=ROOT/'build/diagnostics/driver_shape_source'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    for task in tasks:
        folder=out/task['id'];folder.mkdir(exist_ok=True);old=parent/task['op'];deck=fixture((old/'bench.cir').read_text(),old,folder,task)
        for n,text in [('source.spice',source),('bench.cir',deck)]:
            p=folder/n
            if p.exists() and p.read_text()!=text:raise ValueError('Prepared source PVT fixture changed')
            if not p.exists():p.write_text(text)
        task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir']}
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out,jobs=2):
    if jobs not in [1,2] or not out.is_relative_to(ROOT/'build/diagnostics/driver_shape_source'):raise ValueError('Use prepared source matrix with one or two workers')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json');req=json.loads((ROOT/'requirements.json').read_text())
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items())):raise ValueError('Source waveform matrix changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if [{k:v for k,v in t.items() if k!='files'} for t in m['tasks']]!=cases(req) or (out/'state.json').exists():raise ValueError('Incomplete or prior source matrix')
        if any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','bench.cir.prn','ngspice.log','summary.json']):raise ValueError('Partial source output retained')
        atomic(out/'state.json',dict(status='running_source_pvt',max_jobs=jobs,qualified_phy=False))
        def execute(task):
            folder=out/task['id'];unchanged()
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Source PVT fixture changed')
            atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False));p=None;metrics=None;dc=None;error=None
            try:
                with lease(ROOT,priority=1,label='driver_shape_'+task['id']):
                    unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                    p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged()
                metrics=shape.pilot.measure(folder,'taper_16_32_64');dc=shape.initial_dc(*shape.read_wave(folder/'bench.cir.prn'))
            except Exception as caught:error=str(caught)
            result=dict(task=task['op'],case=task['id'],returncode=None if p is None else p.returncode,metrics=metrics,initial_dc=dc,error=error,qualified_phy=False,manifest_sha256=stamp,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',result);atomic(folder/'execution.json',dict(status='completed' if error is None else 'held_for_diagnosis',qualified_phy=False));return result
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(execute,m['tasks']))
        unchanged();points=[]
        for process,temp in itertools.product(req['process_corners'],req['temperatures_c']):
            rows=[r for r in results if r['case'] in [f'{process}_{temp}_{op}' for op in shape.CASES]];waveforms={};error=None
            try:
                if any(r['error'] is not None or r['metrics'] is None for r in rows):raise ValueError('Source case incomplete')
                low,high=[r['initial_dc']['differential_v'] for r in rows]
                waveforms={r['task']:shape.transitions(*shape.read_wave(out/r['case']/'bench.cir.prn'),low,high) for r in rows}
            except (ValueError,OSError,KeyError) as caught:error=str(caught)
            points.append(dict(process=process,temperature=temp,passed=error is None and pair_checks(rows,waveforms,req),calibrated_transitions=waveforms,error=error))
        passed=len(points)==15 and all(p['passed'] for p in points);unchanged()
        capture_manifest(out/'summary.json',dict(source_waveform_matrix_passed=passed,required_cases=30,required_pvt=15,passed_pvt=sum(p['passed'] for p in points),results=results,pvt=points,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_source_matrix' if passed else 'held_source_checks_failed',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--jobs',type=int,choices=[1,2],default=2);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve(),a.jobs)
