#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check native frequency-step and clock-loss recovery at measured limiting corners."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path

from dll_campaign import atomic,bias_reference_count
from dll_signoff_cases import recovery_cases
from qualify_dll_candidate import validate,execute,evaluate,loop_fixture
from spice_engine import provenance
from spice_probes import ProbeNetwork
from stability_evidence import verified as stability_verified

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(qualification,stability):
    if stability.parent.parent.parent!=qualification:
        raise ValueError('Stability model belongs to another qualification artifact')
    manifest=json.loads((qualification/'manifest.json').read_text());validate(qualification,manifest)
    complete=json.loads((qualification/'summary.json').read_text())
    if not (complete['passed'] and complete['manifest_sha256']==digest(qualification/'manifest.json') and
            set(complete['tasks'])=={t['id'] for t in manifest['tasks']} and
            all(t['status']=='passed' for t in complete['tasks'].values())):
        raise ValueError('Complete native electrical qualification must pass first')
    req=json.loads((qualification/'requirements.json').read_text())
    corners=tuple(f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c'])
    report=stability_verified(stability,manifest['identity']['full_models']['inputs'],corners)
    return manifest,report


def matches(task,process,temp,target):
    s=task['spec']
    return (not task['fast_rc'] and s['kind']=='loop' and s['process']==process and s['temperature']==temp and
        s['mhz']==400 and s['duty']==.5 and
        (bool(s.get('interruption')) and not s.get('step_mhz') if target is None else s.get('step_mhz')==target and not s.get('interruption')))


def identity(qualification,stability):
    return dict(qualification_manifest_sha256=digest(qualification/'manifest.json'),
        stability=str(stability.relative_to(ROOT)),stability_sha256=digest(stability),
        simulator_provenance=provenance(),code={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/dll_signoff_cases.py']})


def verify(path):
    path=Path(path).resolve();root=path.parent;qualification=root.parent.parent
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Recovery evidence outside candidate qualification')
    report=json.loads(path.read_text());manifest=json.loads((root/'manifest.json').read_text())
    stability=ROOT/manifest['identity']['stability']
    q,model=inputs(qualification,stability)
    if (manifest['identity']!=identity(qualification,stability) or not report['passed'] or
        report['manifest_sha256']!=digest(root/'manifest.json')):
        raise ValueError('Failed or stale recovery evidence')
    expected=set(recovery_cases(model));actual=set()
    if len(report['results'])!=len(manifest['tasks']):raise ValueError('Incomplete recovery evidence')
    for task,result in zip(manifest['tasks'],report['results']):
        spec=task['spec'];case=(spec['process'],spec['temperature'],None if spec.get('interruption') else spec.get('step_mhz'))
        if case in actual or not matches(task,*case):raise ValueError('Invalid recovery case')
        actual.add(case);folder=qualification/task['id']
        measured=evaluate(qualification,task)
        if (not result['passed'] or not measured['passed'] or result['task']!=task['id'] or result['metrics']!=measured or
            task['deck_sha256']!=digest(folder/'bench.cir')):
            raise ValueError('Native recovery reanalysis failed')
        for name,stamp in result['files'].items():
            if name not in ['bench.cir','bench.cir.prn','summary.json'] or digest(folder/name)!=stamp:
                raise ValueError('Native recovery evidence changed')
        if set(result['files'])!={'bench.cir','bench.cir.prn','summary.json'}:
            raise ValueError('Missing recovery artifacts')
    if actual!=expected:raise ValueError('Limiting-corner recovery coverage incomplete')
    return report


def run(qualification,stability,jobs=6):
    qualification=qualification.resolve();stability=stability.resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use an isolated DLL qualification artifact')
    q,model=inputs(qualification,stability);stamp=identity(qualification,stability)
    root=qualification/'recovery'/hashlib.sha256(json.dumps(stamp,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        tasks=[];library=(qualification/'full.spice').read_text();network=ProbeNetwork(library)
        for process,temp,target in recovery_cases(model):
            existing=[t for t in q['tasks'] if matches(t,process,temp,target)]
            if len(existing)>1:raise ValueError('Ambiguous original recovery case')
            if existing:tasks.append(existing[0]);continue
            label=f'{process}_{temp}_'+('clock_loss' if target is None else str(target))
            folder=root/label;folder.mkdir(exist_ok=True)
            spec=dict(kind='loop',process=process,temperature=temp,mhz=400,duty=.5,
                architecture='averaged_pfd_ota',step_mhz=target,interruption=target is None)
            body,probes,stop,timing=loop_fixture(spec,q['identity']['full_models']['observation_nodes'])
            pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
            text=(f'OpenLVDS limiting-corner recovery {label}\n.lib "{pdk}" {process}\n'
                f'.include "{qualification}/full.spice"\n.options device temp={temp}\n'
                '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
                f'.save i(VA) i(VD)\n.tran 5p {stop}n 0 20p\n.print tran '+
                ' '.join('V('+node+')' for node in probes.values())+'\n.end\n')
            if bias_reference_count(text,library)!=1:raise ValueError('Recovery fixture duplicates its reference bias')
            network.validate(text,probes.values());deck=folder/'bench.cir'
            if deck.exists() and deck.read_text()!=text:raise ValueError('Recovery fixture changed')
            deck.write_text(text)
            tasks.append(dict(id=str(folder.relative_to(qualification)),spec=dict(spec,stop_ns=stop,**timing),
                aliases=probes,fast_rc=False,deck_sha256=digest(deck)))
        atomic(root/'manifest.json',dict(identity=stamp,tasks=tasks))
        def measure(task):
            record=execute(qualification,q,task);folder=qualification/task['id']
            return dict(task=task['id'],passed=record['passed'],metrics=record.get('metrics'),
                files={name:digest(folder/name) for name in ['bench.cir','bench.cir.prn','summary.json'] if (folder/name).exists()})
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(measure,tasks))
        inputs(qualification,stability)
        atomic(root/'summary.json',dict(passed=all(r['passed'] for r in results),qualified_phy=False,
            manifest_sha256=digest(root/'manifest.json'),results=results))
        if all(r['passed'] for r in results):verify(root/'summary.json')
        print(root/'summary.json',flush=True)
        return 0 if all(r['passed'] for r in results) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path)
    p.add_argument('--stability',required=True,type=Path);p.add_argument('--jobs',type=int,choices=range(1,7),default=6)
    a=p.parse_args();return run(a.qualification,a.stability,a.jobs)


if __name__=='__main__':raise SystemExit(main())
