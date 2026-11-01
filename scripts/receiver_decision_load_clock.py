#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the original three source clock controls after full stronger-PMOS DC admission."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path

import numpy as np
from dll_campaign import atomic
from dll_measurements import read_wave
import receiver_decision_load_experiment as factory
import receiver_decision_load_matrix as dc
from receiver_static_diagnosis import capture_manifest
from receiver_tail_timestep_retry import tighten
from rx_candidate_aperture import lease

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
CASES={'unclamped_captured','clamped_captured','clamped_sharp_control'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def admitted(summary):
    results=summary.get('results',[])
    return (summary.get('diagnostic_complete') is True and len(results)==3 and
        {r['task'] for r in results}==CASES and
        all(not r['receiver_transport']['missing_output_edges'] and
            len(r['receiver_transport']['pulses'])==47 and
            all(p['output_edges_in_next_input_period']==1 for p in r['receiver_transport']['pulses'])
            for r in results))


def static_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_decision_load_matrix'):
        raise ValueError('Use the prepared stronger-PMOS DC matrix')
    manifest=json.loads((screen/'manifest.json').read_text())
    children=manifest['identity']['children']
    if (len(children)!=15 or not (screen/'summary.json').exists() or
            any(not (ROOT/c['root']/'summary.json').exists() for c in children)):
        raise ValueError('Complete all fifteen original DC cases before the clock screen')
    # All cases already exist, so the scientific runner can only remeasure.
    # Serialize consumers separately from its own nonblocking execution lock.
    with (screen/'.clock_admission.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        result=dc.run(screen)
    if result.get('dc_all_passed') is not True or result.get('required')!=15:
        raise ValueError('Stronger-PMOS DC matrix must pass every original case')
    paths=[screen/'manifest.json',screen/'summary.json']
    for child in children:
        folder=ROOT/child['root']
        paths.extend(folder/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn'])
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def derive(base,screen,proofs):
    previous=json.loads((base/'manifest.json').read_text());identity=copy.deepcopy(previous['identity'])
    if len(previous['tasks'])!=3 or {t['id'] for t in previous['tasks']}!=CASES:
        raise ValueError('Expected exactly the three original source controls')
    identity.update(static_screen=str(screen.relative_to(ROOT)),
        numerical_policy=dict(maximum_step_ps=1,output_step_ps=5,stop_ns=80,analysis_window_ns=[15,75]),
        static_proofs=proofs)
    identity['inputs'].update(proofs)
    identity['inputs'][str((base/'manifest.json').relative_to(ROOT))]=digest(base/'manifest.json')
    for task in previous['tasks']:
        for name,stamp in task['files'].items():
            path=base/task['id']/name
            if digest(path)!=stamp:raise ValueError('Source template fixture changed')
            identity['inputs'][str(path.relative_to(ROOT))]=stamp
    root=ROOT/'build/diagnostics/receiver_clamp'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True);tasks=copy.deepcopy(previous['tasks'])
    for task in tasks:
        old=base/task['id'];folder=root/task['id'];folder.mkdir(exist_ok=True)
        for name in task['files']:
            text=(old/name).read_text()
            if name=='bench.cir':
                before=f'.include "{old}/library.spice"';after=f'.include "{folder}/library.spice"'
                if text.count(before)!=1:raise ValueError('Ambiguous original clock library inclusion')
                text=tighten(text.replace(before,after))
            path=folder/name
            if path.exists() and path.read_text()!=text:raise ValueError('Source clock fixture changed')
            if not path.exists():path.write_text(text)
        task['files']={n:digest(folder/n) for n in task['files']}
    capture_manifest(root/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
    return root


def prepare(parent,screen):
    proofs=static_gate(screen)
    original=factory.experiment.CODE
    try:
        factory.experiment.CODE=sorted(set(original)|set(dc.diagnosis.CODE)|{
            NAME,'receiver_decision_load_matrix.py','receiver_tail_timestep_retry.py'})
        base=factory.prepare(parent)
    finally:factory.experiment.CODE=original
    return derive(base,screen,proofs)


def run(root,wait_slot=None):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the isolated stronger-PMOS source clock screen')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    if identity['code'].get(NAME)!=digest(Path(__file__)) or identity.get('numerical_policy')!=dict(
            maximum_step_ps=1,output_step_ps=5,stop_ns=80,analysis_window_ns=[15,75]):
        raise ValueError('Source clock numerical policy or producer changed')
    screen=(ROOT/identity['static_screen']).resolve()
    if static_gate(screen)!=identity['static_proofs']:raise ValueError('Source DC admission changed')
    if len(manifest['tasks'])!=3 or {t['id'] for t in manifest['tasks']}!=CASES:
        raise ValueError('Incomplete original source clock coverage')
    for task in manifest['tasks']:
        folder=root/task['id'];deck=(folder/'bench.cir').read_text()
        if tighten(deck)!=deck or (folder/'candidate.spice').read_text()!=factory.source_variant(
                (ROOT/'analog/openlvds.spice').read_text(),task['clamped']):
            raise ValueError('Source clock circuit or numerical policy differs from declaration')
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw','ngspice.log','bench.cir.prn']):
            raise ValueError('Incomplete prior source execution retained; use a fresh context for retry')
    original=factory.experiment.slot
    scheduling=dict(manifest_sha256=digest(root/'manifest.json'),wait_slot=wait_slot,global_slot_budget=6,
        producer_sha256=digest(Path(__file__)),qualified_phy=False)
    folder=root/'execution_scheduling'/hashlib.sha256(json.dumps(scheduling,sort_keys=True).encode()).hexdigest()[:16]
    folder.mkdir(parents=True,exist_ok=True);capture_manifest(folder/'manifest.json',scheduling)
    try:
        factory.experiment.slot=lambda:lease(wait_slot)
        factory.experiment.run(root)
    finally:factory.experiment.slot=original
    for task in manifest['tasks']:
        wave,_=read_wave(root/task['id']/'bench.cir.prn');t=wave[:,1]
        if len(t)<2 or t[0]>1e-15 or t[-1]<80e-9-1e-12 or not np.isfinite(wave).all() or np.any(np.diff(t)<=0):
            raise ValueError('Incomplete full source clock waveform')
    if any(digest(ROOT/n)!=stamp for n,stamp in identity['static_proofs'].items()):
        raise ValueError('DC admission changed during the clock screen')
    summary=json.loads((root/'summary.json').read_text())
    passed=admitted(summary)
    atomic(root/'source_clock_admission.json',dict(source_clock_passed=passed,qualified_phy=False,
        manifest_sha256=digest(root/'manifest.json'),report_sha256=digest(root/'summary.json'),
        scope='All original three source controls, 47 periods each; no physical or native admission'))
    if not passed:raise ValueError('Source clock screen loses or repeats an original edge')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--dc-matrix',type=Path);parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':
        if args.dc_matrix is None:parser.error('--dc-matrix is required for preparation')
        print(prepare(args.artifact.resolve(),args.dc_matrix.resolve()),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
