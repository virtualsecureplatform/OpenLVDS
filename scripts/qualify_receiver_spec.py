#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Use fresh specification screening to admit the unchanged sixty RX component tests."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import qualify_receiver_components as components
import receiver_spec_screen as screen
import spice_slots
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import provenance

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
sha=screen.sha


def recheck(artifact,replay):
    if not artifact.is_relative_to(ROOT/'build/diagnostics/receiver_spec_screen'):raise ValueError('Require specification screen admission')
    m=json.loads((artifact/'manifest.json').read_text());i=m['identity'];stamp=sha(artifact/'manifest.json')
    if i['replay']!=str(replay.relative_to(ROOT)):raise ValueError('Screen characterizes another receiver')
    if artifact.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:raise ValueError('Screen identity changed')
    if provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Screen evidence changed')
    expected=screen.cases(json.loads((ROOT/'requirements.json').read_text()))
    if [{k:v for k,v in t.items() if k not in ['files','stop_ns']} for t in m['tasks']]!=expected:raise ValueError('Screen coverage changed')
    # Never invoke an unfinished producer from an admission check.
    if not (artifact/'summary.json').exists() or any(not (artifact/t['id']/'summary.json').exists() for t in m['tasks']):raise ValueError('Complete all 33 specification cases before admission')
    paths=[artifact/'manifest.json',artifact/'summary.json'];results=[]
    with (artifact/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in m['tasks']:
            folder=artifact/task['id'];report=json.loads((folder/'summary.json').read_text())
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Screen fixture changed')
            if report.get('passed') is not True or report.get('numerical_or_export_failure'):raise ValueError('Specification screen failed; retain legacy diagnostics')
            w,h=screen.read_wave(folder/'bench.cir.prn')
            measured=dict(task=task['id'],**screen.measure(w,h,task),waveform_sha256=sha(folder/'bench.cir.prn'),manifest_sha256=stamp,qualified_phy=False)
            if measured!=report:raise ValueError('Specification result differs from waveform')
            results.append(measured);paths += [folder/n for n in ['summary.json','bench.cir.prn','bench.cir','library.spice']]
        expected_summary=dict(results=results,passed=True,required=33,manifest_sha256=stamp,qualified_phy=False,scope=i['scope'])
        if json.loads((artifact/'summary.json').read_text())!=expected_summary:raise ValueError('Specification screen aggregate changed')
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


@contextmanager
def selection(artifact,replay):
    previous=components.CODE,components.replay_ready,spice_slots.slot
    try:
        components.CODE=sorted(set(components.CODE)|set(screen.CODE)|{NAME})
        components.replay_ready=lambda selected: recheck(artifact,selected)
        spice_slots.slot=lambda:lease(ROOT,priority=1,label='spec_receiver_components')
        yield
    finally:components.CODE,components.replay_ready,spice_slots.slot=previous


def prepare(artifact):
    i=json.loads((artifact/'manifest.json').read_text())['identity'];replay=ROOT/i['replay']
    proofs=recheck(artifact,replay)
    with selection(artifact,replay):out=components.prepare(ROOT/i['layout'],replay)
    capture_manifest(out/'spec_admission.json',dict(screen=str(artifact.relative_to(ROOT)),proofs=proofs,
        component_manifest_sha256=sha(out/'manifest.json'),producer_sha256=sha(Path(__file__)),qualified_phy=False,
        scope='Specification screen admission to original sixty components only. Legacy verdict unchanged. Full corrected loopback and every release gate remain required.'))
    return out


def run(out,jobs=2):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_components'):raise ValueError('Use prepared component matrix')
    proof=json.loads((out/'spec_admission.json').read_text());m=json.loads((out/'manifest.json').read_text())
    if proof['producer_sha256']!=sha(Path(__file__)) or proof['component_manifest_sha256']!=sha(out/'manifest.json'):raise ValueError('Specification component admission changed')
    artifact=ROOT/proof['screen'];replay=ROOT/m['identity']['replay']
    if recheck(artifact,replay)!=proof['proofs']:raise ValueError('Specification proof changed')
    for t in m['tasks']:
        folder=out/t['id']
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):raise ValueError('Partial component output retained')
    with selection(artifact,replay):components.run(out,jobs)
    return out/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--jobs',type=int,choices=[1,2,3],default=2);a=p.parse_args()
    print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve(),a.jobs),flush=True)
