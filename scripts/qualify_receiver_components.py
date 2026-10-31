#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify isolated receiver schematic/native components with original fixtures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import numpy as np

from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from probe_receiver_candidate_link import replay_ready
from reduce_rc import number
from spice_engine import command,engine,provenance
from spice_library import library,checked_netlist
from spice_probes import ProbeNetwork
from stage_phy_candidate import overlay
from verify_analog import receiver_rate_metrics
from verify_component_evidence import check_case

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
CODE=['qualify_receiver_components.py','verify_analog.py','verify_component_evidence.py','evidence_scope.py',
      'dll_campaign.py','dll_candidate_library.py','dll_measurements.py','spice_engine.py','spice_library.py',
      'spice_scope.py','spice_probes.py','spice_slots.py','run_ngspice.py','reduce_rc.py',
      'stage_phy_candidate.py','probe_receiver_candidate_link.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(requirements):
    result=list(itertools.product(['schematic','native'],['receiver','receiver_rate'],
                requirements['process_corners'],requirements['temperatures_c']))
    if len(set(result))!=len(result):raise ValueError('Duplicate receiver qualification condition')
    return result


def rebind(deck,old,new):
    include=f'.include "{old}/source.spice"'
    if deck.count(include)!=1:raise ValueError('Expected one captured source inclusion')
    return deck.replace(include,f'.include "{new}/source.spice"')


def static_metrics(wave):
    if wave[-1,1]<144e-9-1e-12:raise ValueError('Incomplete static receiver transient')
    points=[]
    for index in range(12):
        at=index*12+10;high=bool(index%2);value=float(np.interp(at*1e-9,wave[:,1],wave[:,4]))
        points.append(dict(time_ns=at,expected=high,output_v=value,passed=value>1.44 if high else value<.36))
    return dict(passed=all(p['passed'] for p in points),points=points)


def check_coverage(tasks,requirements):
    actual=[(t['view'],t['test'],t['process'],t['temperature']) for t in tasks]
    if len(actual)!=len(cases(requirements)) or set(actual)!=set(cases(requirements)):
        raise ValueError('Incomplete or duplicate receiver component coverage')
    if any(t['id']!=f"{t['view']}_{t['test']}_{t['process']}_{t['temperature']}" for t in tasks):
        raise ValueError('Receiver component case name differs from condition')


def fixture(old,folder,model,view):
    body=overlay((old/'source.spice').read_text(),model,TOP,('lvds_bias','openlvds_driver','openlvds_delay_line'))
    deck=rebind((old/'bench.cir').read_text(),old,folder)
    if view=='native':
        for leaf in ['PP','PN','CO']:
            matches=sorted(set(re.findall(r'\b'+TOP+'__'+leaf+r'(?:\.t\d+)?\b',model)))
            if not matches:raise ValueError('Missing native receiver observation '+leaf)
            deck=deck.replace('XR:XCORE:'+TOP+'__'+leaf,'XR:XCORE:'+matches[0])
    probes=re.search(r'(?im)^\.print tran[^\n]*',deck)
    ProbeNetwork(body).validate(deck,re.findall(r'V\(([^)]+)\)',probes[0],re.I))
    stop=number(re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',deck)[1])
    return body,deck,stop


def prepare(layout,replay):
    if engine()!='ngspice' or not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout') or not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use isolated receiver artifacts in the pinned ngspice environment')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    if not physical['passed'] or (layout/'rejected_candidate.json').exists():raise ValueError('Physical receiver failed')
    audited(layout,info);gds=ROOT/physical['designs'][TOP]['gds'];source=layout/'candidate.spice'
    if digest(gds)!=info['gds_sha256'] or digest(source)!=info['source_sha256']:
        raise ValueError('Receiver physical source changed')
    capture=json.loads((replay/'manifest.json').read_text())
    if capture['identity']['layout']!=str(layout.relative_to(ROOT)):raise ValueError('Replay characterizes another receiver')
    names=set(CODE)|set(capture['identity']['code'])|set(physical['identity']['code'])
    for name,value in physical['identity']['code'].items():
        if digest(ROOT/'scripts'/name)!=value:raise ValueError('Physical receiver producer changed')
    req=json.loads((ROOT/'requirements.json').read_text());stamp=provenance()
    base_source=(ROOT/'analog/openlvds.spice').read_bytes()
    native,inputs,_=library(extracted=True,designs={TOP,'lvds_bias'})
    paths=[layout/n for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']]
    paths += [gds,ROOT/info['netlist'],replay/'manifest.json',ROOT/'requirements.json',ROOT/'analog/openlvds.spice',
              ROOT/'build/extracted/current.json',ROOT/'build/layout/current.json']
    fixtures=[]
    for view,test,corner,temp in cases(req):
        old=ROOT/'build'/('analog' if view=='schematic' else 'analog_extracted')/f'{test}_{corner}_{temp}'
        proof=check_case(old,test,base_source if view=='schematic' else native,{} if view=='schematic' else inputs,
                         digest(ROOT/'scripts/verify_analog.py'),digest(ROOT/'requirements.json'),engine(),stamp)
        if not proof['passed']:raise ValueError('Original receiver fixture is stale or failed: '+str(old))
        paths += [old/n for n in ['bench.cir','source.spice','summary.json','bench.cir.prn','runner.py']]
        fixtures.append((view,test,corner,temp,old))
    identity=dict(layout=str(layout.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
                  inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},
                  code={n:digest(ROOT/'scripts'/n) for n in names},simulator_provenance=stamp,
                  requirements_sha256=digest(ROOT/'requirements.json'))
    root=ROOT/'build/diagnostics/receiver_components'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True);tasks=[]
    for view,test,corner,temp,old in fixtures:
        name=f'{view}_{test}_{corner}_{temp}';folder=root/name;folder.mkdir()
        model=source.read_text() if view=='schematic' else checked_netlist(info)
        body,deck,stop=fixture(old,folder,model,view)
        (folder/'source.spice').write_text(body);(folder/'bench.cir').write_text(deck)
        tasks.append(dict(id=name,view=view,test=test,process=corner,temperature=temp,stop_seconds=stop,
                          files={n:digest(folder/n) for n in ['source.spice','bench.cir']}))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,required=len(tasks),qualified_phy=False))
    return root


def run(root,jobs):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_components'):raise ValueError('Use a prepared component campaign')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=v for n,v in identity['code'].items()):
            raise ValueError('Receiver qualification producer changed')
        if any(digest(ROOT/n)!=v for n,v in identity['inputs'].items()):raise ValueError('Receiver qualification input changed')
    def execute(task):
        from spice_slots import slot
        folder=root/task['id'];summary=folder/'summary.json';cached=None
        for name,value in task['files'].items():
            if digest(folder/name)!=value:raise ValueError('Receiver component fixture changed')
        if summary.exists():
            cached=json.loads(summary.read_text())
            if digest(folder/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Receiver component waveform changed')
        else:
            atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with slot():
                unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
        wave,header=read_wave(folder/'bench.cir.prn')
        if (wave.ndim!=2 or wave.shape[1]<5 or header.get('V(Q)')!=4 or not np.isfinite(wave).all() or
            wave[-1,1]<task['stop_seconds']-1e-12 or np.any(np.diff(wave[:,1])<=0)):
            raise ValueError('Incomplete or invalid receiver component waveform')
        measured=static_metrics(wave) if task['test']=='receiver' else receiver_rate_metrics(wave)
        result=dict(task=task['id'],**measured,qualified_phy=False,manifest_sha256=digest(root/'manifest.json'),
                    waveform_sha256=digest(folder/'bench.cir.prn'),deck_sha256=task['files']['bench.cir'])
        if cached is not None and cached!=result:raise ValueError('Receiver component analysis differs from waveform')
        atomic(summary,result)
        atomic(folder/'execution.json',dict(status='completed',passed=result['passed'],qualified_phy=False))
        return result
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        expected_root=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        if root.name!=expected_root:raise ValueError('Receiver component identity changed')
        req=json.loads((ROOT/'requirements.json').read_text());check_coverage(manifest['tasks'],req)
        layout=ROOT/identity['layout'];info=json.loads((layout/'extraction.json').read_text())
        for task in manifest['tasks']:
            old=ROOT/'build'/('analog' if task['view']=='schematic' else 'analog_extracted')/f"{task['test']}_{task['process']}_{task['temperature']}"
            model=(layout/'candidate.spice').read_text() if task['view']=='schematic' else checked_netlist(info)
            body,deck,stop=fixture(old,root/task['id'],model,task['view'])
            if (body!=(root/task['id']/'source.spice').read_text() or deck!=(root/task['id']/'bench.cir').read_text()
                or stop!=task['stop_seconds']):
                raise ValueError('Receiver component differs from original fixture or selected model')
        replay_ready(ROOT/identity['replay'])
        def safe(task):
            try:return execute(task)
            except Exception as error:
                atomic(root/task['id']/'execution.json',dict(status='failed',error=str(error),qualified_phy=False))
                return dict(task=task['id'],passed=False,error=str(error),qualified_phy=False)
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(safe,manifest['tasks']))
        unchanged()
        req=json.loads((ROOT/'requirements.json').read_text())
        actual={(t['view'],t['test'],t['process'],t['temperature']) for t in manifest['tasks']}
        complete=len(manifest['tasks'])==len(cases(req)) and actual==set(cases(req))
        atomic(root/'summary.json',dict(passed=complete and all(r['passed'] for r in results),qualified_phy=False,
            required=len(cases(req)),passed_cases=sum(r['passed'] for r in results),results=results,
            manifest_sha256=digest(root/'manifest.json'),
            scope='Selected receiver schematic/native static and rate component cases only; no DLL, aperture, headroom or full-link qualification'))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('layout',type=Path);a.add_argument('replay',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a.add_argument('--jobs',type=int,choices=range(1,7),default=3)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.layout.resolve(),a.replay.resolve()),flush=True)
    else:run(a.artifact.resolve(),a.jobs)
