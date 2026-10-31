#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind readiness RTL replay to native all-PVT acquisition and late clock loss."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

from dll_campaign import atomic,bias_reference_count
from dll_measurements import read_wave,loop
from dll_readiness_replay import replay,analyze,backend,input_events
from dll_signoff_cases import BASE_CORNERS,limiting_corners
from measure_dll_stability import transient
from qualify_dll_candidate import loop_fixture
from qualify_dll_recovery import inputs,verify as recovery_verified
from spice_engine import provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
STOP_NS=4700


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def clock_wave():
    points=[(0,0)]
    for at in range(5000,STOP_NS*1000,2500):
        if 2200000<=at<2300000:continue
        points.extend([(at-50,0),(at+50,1.8),(at+1200,1.8),(at+1300,0)])
    return 'VCLK CLK 0 PWL('+' '.join(f'{at}p {v:g}' for at,v in points)+')\n'


def loss_fixture(process,temp,observations):
    body,probes,_,_=loop_fixture(dict(kind='loop',process=process,temperature=temp,mhz=400,
        duty=.5,interruption=True,architecture='averaged_pfd_ota'),observations)
    body=re.sub(r'(?m)^VCLK[^\n]*\n',lambda _:clock_wave(),body)
    body=re.sub(r'(?m)^VEN[^\n]*\n',
        'VEN ENABLE 0 PWL(0 0 85.2n 0 85.22n 1.8 2210n 1.8 2210.02n 0 2380.2n 0 2380.22n 1.8)\n',body)
    return body,probes


def stamp(qualification,stability,recovery):
    return dict(qualification_manifest_sha256=digest(qualification/'manifest.json'),
        stability=str(stability.relative_to(ROOT)),stability_sha256=digest(stability),
        recovery=str(recovery.relative_to(ROOT)),recovery_sha256=digest(recovery),
        simulator_provenance=provenance(),rtl_backend=backend(),
        code={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'scripts/dll_readiness_replay.py',
            ROOT/'scripts/dll_signoff_cases.py',ROOT/'scripts/qualify_dll_recovery.py',
            ROOT/'scripts/measure_dll_stability.py',ROOT/'rtl/openlvds_dll_control.v']})


def aliases(wave,header,mapping):
    for name,node in mapping.items():header['V('+name.upper()+')']=header['V('+node.upper()+')']
    return wave,header


def cases(q,model,stability):
    tasks=[]
    for result in model['results']:
        corner=result['corner'];process,temp=corner.rsplit('_',1)
        source=next(t for t in q['tasks'] if t['id']=='loop_'+corner)
        for target in [390,410]:
            tasks.append(dict(id=f'step_{corner}_{target}',kind='step',process=process,temperature=int(temp),
                aliases=source['aliases'],source=str((stability.parent/corner/f'step_{target}/bench.cir.prn').relative_to(ROOT))))
    for process,temp in sorted(BASE_CORNERS|limiting_corners(model)):
        _,probes=loss_fixture(process,temp,q['identity']['full_models']['observation_nodes'])
        tasks.append(dict(id=f'loss_{process}_{temp}',kind='loss',process=process,temperature=temp,aliases=probes))
    return tasks


def verify(path):
    path=path.resolve();root=path.parent;qualification=root.parent.parent
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Readiness evidence outside candidate qualification')
    report=json.loads(path.read_text());manifest=json.loads((root/'manifest.json').read_text())
    identity=manifest['identity'];stability=ROOT/identity['stability'];recovery=ROOT/identity['recovery']
    if recovery.parent.parent.parent!=qualification:raise ValueError('Recovery belongs to another candidate')
    q,model=inputs(qualification,stability);recovery_verified(recovery)
    if not report['passed'] or identity!=stamp(qualification,stability,recovery) or report['manifest_sha256']!=digest(root/'manifest.json'):
        raise ValueError('Readiness producer or inputs changed')
    expected={f'step_{r["corner"]}_{target}' for r in model['results'] for target in [390,410]}
    expected|={f'loss_{p}_{t}' for p,t in BASE_CORNERS|limiting_corners(model)}
    if manifest['tasks']!=cases(q,model,stability) or {t['id'] for t in manifest['tasks']}!=expected or len(manifest['tasks'])!=len(expected) or len(report['results'])!=len(expected):
        raise ValueError('Incomplete native readiness coverage')
    for task,result in zip(manifest['tasks'],report['results']):
        folder=root/task['id'];source=ROOT/result['source_waveform']
        if not source.resolve().is_relative_to(qualification) or digest(source)!=result['waveform_sha256']:
            raise ValueError('Native readiness input waveform changed')
        expected_source=ROOT/task['source'] if task['kind']=='step' else folder/'native/bench.cir.prn'
        if source.resolve()!=expected_source.resolve():raise ValueError('Readiness waveform belongs to another case')
        wave,header=aliases(*read_wave(source),task['aliases'])
        measured=analyze(wave,header,(folder/'replay.log').read_text(),task['kind']=='loss')
        if result['id']!=task['id'] or not result['passed'] or not measured['passed'] or result['metrics']!=measured:
            raise ValueError('Native readiness reanalysis failed')
        if task['kind']=='loss':
            settled=loop(wave,header,400,'averaged_pfd_ota',4300,4600)
            if not settled['passed'] or result['settled_recovery']!=settled:raise ValueError('Late recovery is not settled')
        stimulus=''.join(f'{dt} {bits}\n' for dt,bits in input_events(wave,header,task['kind']=='loss'))
        if (folder/'stimulus.txt').read_text()!=stimulus:raise ValueError('Readiness stimulus differs from native edges')
        if not {'stimulus.txt','bench.v','replay.log','replay.vvp','compile.log'}<=set(result['files']):
            raise ValueError('Incomplete RTL replay artifacts')
        for name,value in result['files'].items():
            target=folder/name
            if not target.resolve().is_relative_to(folder) or digest(target)!=value:
                raise ValueError('Readiness replay artifact changed')
    return report


def run(qualification,stability,recovery,jobs):
    qualification=qualification.resolve();stability=stability.resolve();recovery=recovery.resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification') or recovery.parent.parent.parent!=qualification:
        raise ValueError('Use recovery evidence from the same isolated candidate')
    q,model=inputs(qualification,stability);recovery_verified(recovery)
    identity=stamp(qualification,stability,recovery)
    root=qualification/'readiness'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        tasks=cases(q,model,stability)
        atomic(root/'manifest.json',dict(identity=identity,tasks=tasks))
        library=(qualification/'full.spice').read_text();network=ProbeNetwork(library)
        def measure(task):
            folder=root/task['id'];folder.mkdir(exist_ok=True)
            if task['kind']=='loss':
                body,probes=loss_fixture(task['process'],task['temperature'],q['identity']['full_models']['observation_nodes'])
                pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
                text=(f'OpenLVDS native late clock loss {task["id"]}\n.lib "{pdk}" {task["process"]}\n'
                    f'.include "{qualification}/full.spice"\n.options device temp={task["temperature"]}\n'
                    '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                    'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
                    f'.tran 5p {STOP_NS}n 0 20p\n.print tran '+' '.join('V('+node+')' for node in probes.values())+'\n.end\n')
                if bias_reference_count(text,library)!=1:raise ValueError('Readiness fixture duplicates reference bias')
                network.validate(text,probes.values());wave,header=transient(folder/'native',text)
                source=folder/'native/bench.cir.prn'
            else:source=ROOT/task['source'];wave,header=read_wave(source)
            wave,header=aliases(wave,header,task['aliases'])
            metrics=replay(wave,header,folder,task['kind']=='loss')
            settled=loop(wave,header,400,'averaged_pfd_ota',4300,4600) if task['kind']=='loss' else None
            result=dict(id=task['id'],passed=bool(metrics['passed'] and (settled is None or settled['passed'])),
                metrics=metrics,settled_recovery=settled,source_waveform=str(source.relative_to(ROOT)),waveform_sha256=digest(source),
                files={str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file() and p.name!='summary.json'})
            atomic(folder/'summary.json',result);print(task['id'],result['passed'],flush=True);return result
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(measure,tasks))
        if stamp(qualification,stability,recovery)!=identity:raise ValueError('Readiness inputs changed during replay')
        atomic(root/'summary.json',dict(passed=all(r['passed'] for r in results),qualified_phy=False,
            manifest_sha256=digest(root/'manifest.json'),results=results))
        if all(r['passed'] for r in results):verify(root/'summary.json')
        print(root/'summary.json',flush=True)
        return 0 if all(r['passed'] for r in results) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path)
    p.add_argument('--stability',required=True,type=Path);p.add_argument('--recovery',required=True,type=Path)
    p.add_argument('--jobs',type=int,choices=range(1,7),default=6);a=p.parse_args()
    return run(a.qualification,a.stability,a.recovery,a.jobs)


if __name__=='__main__':raise SystemExit(main())
