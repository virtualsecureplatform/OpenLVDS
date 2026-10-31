#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare an audited exact RC profile with unchanged native SS monitor references."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
from dll_campaign import atomic,text_block
from dll_candidate_library import assemble
from dll_qualification_measurements import compare
from dll_measurements import read_wave,column
from exact_rc_candidate import parse,static_signature
from qualify_dll_candidate import validate,execute
from run_dll_comparison import alive
from spice_engine import provenance
from spice_library import replace

ROOT=Path(__file__).resolve().parents[1]
CASES=['phase_ss_0_0ps','phase_ss_0_50ps']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(layout,reference,manifest):
    validate(reference,manifest)
    captured=json.loads((layout/'manifest.json').read_text());identity=captured['identity']
    if identity['layout']!=manifest['identity']['full_models']['layout'] or identity['source_sha256']!=manifest['identity']['full_models']['inputs']['openlvds_dll_analog']:
        raise ValueError('Exact RC profile is derived from another physical reference')
    for name,value in captured['files'].items():
        if digest(layout/name)!=value:raise ValueError('Exact RC profile artifact changed')
    for name,value in identity['physical_files'].items():
        if digest(ROOT/name)!=value:raise ValueError('Original physical evidence changed')
    for name,value in identity['code'].items():
        if digest(ROOT/'scripts'/name)!=value:raise ValueError('Exact RC producer changed')
    for name,value in identity['math_runtime']['binaries'].items():
        if digest(ROOT/name)!=value:raise ValueError('Independent numerical solver changed')
    if not json.loads((layout/'admittance_witness.json').read_text())['passed']:
        raise ValueError('Exact RC profile lacks passing numerical witnesses')
    full,models=assemble(layout,ROOT/manifest['identity']['full_models']['pfd'])
    baseline=(reference/'full.spice').read_text()
    analog=text_block(full,'openlvds_dll_analog')
    if replace(baseline,'openlvds_dll_analog',analog)!=full:
        raise ValueError('Exact profile changed an unrelated DLL definition')
    if static_signature(parse(analog))!=static_signature(parse(text_block(baseline,'openlvds_dll_analog'))):
        raise ValueError('Exact profile changed a device, capacitor or terminal statement')
    return full,models


def mapped(path,task):
    wave,header=read_wave(path)
    for name,node in task['aliases'].items():header['V('+name.upper()+')']=header['V('+node.upper()+')']
    return wave,header


def native_seconds(folder):
    start=json.loads((folder/'execution.json').read_text())['started_unix']
    return (folder/'summary.json').stat().st_mtime-start


def wait_reference(reference,task,out):
    folder=reference/task['id']
    while not (folder/'summary.json').exists():
        state=json.loads((reference/'state.json').read_text())
        if state.get('tasks',{}).get(task['id'],{}).get('status') in ['failed','skipped']:
            raise ValueError('Original native reference failed')
        records=json.loads((ROOT/'build/diagnostics/resident_jobs/watchdog.json').read_text())['jobs']
        record=records.get('qualify_ota',{})
        if not alive(record.get('pid'),record.get('identity')):
            raise RuntimeError('Reference coordinator is not live; preserve benchmark and resume after recovery')
        atomic(out/'state.json',dict(status='waiting_for_native_reference',task=task['id'],reference_pid=record['pid']))
        time.sleep(10)


def run(layout,reference):
    layout=layout.resolve();reference=reference.resolve()
    if not layout.is_relative_to(ROOT/'build/diagnostics/dll_layout') or not reference.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use isolated physical and native reference artifacts')
    manifest=json.loads((reference/'manifest.json').read_text());full,models=candidate(layout,reference,manifest)
    identity=dict(layout=str(layout.relative_to(ROOT)),layout_manifest_sha256=digest(layout/'manifest.json'),
        reference_manifest_sha256=digest(reference/'manifest.json'),full_sha256=hashlib.sha256(full.encode()).hexdigest(),
        models=models,simulator_provenance=provenance(),producer_sha256=digest(Path(__file__)),cases=CASES)
    root=reference/'rc_equivalence'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        target=root/'full.spice'
        if target.exists() and target.read_text()!=full:raise ValueError('Captured benchmark library changed')
        target.write_text(full);tasks=[]
        for name in CASES:
            original=next(t for t in manifest['tasks'] if t['id']==name)
            source=reference/name/'bench.cir'
            if digest(source)!=original['deck_sha256']:raise ValueError('Original reference fixture changed')
            text,count=re.subn(r'(?m)^\.include "'+re.escape(str(reference/'full.spice'))+'"$',
                lambda _:f'.include "{root}/full.spice"',source.read_text())
            if count!=1:raise ValueError('Original reference library binding is ambiguous')
            folder=root/name;folder.mkdir(exist_ok=True);deck=folder/'bench.cir'
            if deck.exists() and deck.read_text()!=text:raise ValueError('Captured benchmark fixture changed')
            deck.write_text(text)
            tasks.append(dict(original=original,trial=dict(original,id=str(folder.relative_to(reference)),deck_sha256=digest(deck))))
        atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,qualified=False))
        atomic(root/'state.json',dict(status='queued_for_native_slots'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            trials=list(pool.map(lambda pair:execute(reference,manifest,pair['trial']),tasks))
        results=[]
        for pair,trial in zip(tasks,trials):
            original=pair['original'];task=pair['trial'];wait_reference(reference,original,root)
            baseline=execute(reference,manifest,original)
            source=reference/original['id'];trial_folder=reference/task['id']
            a,ha=mapped(source/'bench.cir.prn',original);b,hb=mapped(trial_folder/'bench.cir.prn',task)
            # The generic comparator treats named CTRL/UF/DF as analog. Check
            # additional physical storage plates separately as analog voltages.
            names=[name for name in task['aliases'] if not name.startswith('CTRL_CAP_')]
            check=compare(a,ha,b,hb,names,120,160)
            sample=np.linspace(120e-9,160e-9,8001);plates=[]
            for name in task['aliases']:
                if name!='CTRL' and not name.startswith('CTRL_CAP_'):continue
                error=float(np.max(abs(np.interp(sample,a[:,1],column(a,ha,name))-np.interp(sample,b[:,1],column(b,hb,name)))))
                plates.append(dict(name=name,error_max_v=error,passed=error<=.02))
            old_seconds=native_seconds(source);new_seconds=native_seconds(trial_folder)
            result=dict(case=original['id'],passed=bool(baseline['passed'] and trial['passed'] and check['passed'] and all(p['passed'] for p in plates)),
                comparison=check,storage_plates=plates,reference_native_seconds=old_seconds,trial_native_seconds=new_seconds,
                speedup_excluding_slot_wait=old_seconds/new_seconds,
                files={str(p.relative_to(reference)):digest(p) for folder in [source,trial_folder]
                       for name in ['bench.cir','bench.cir.prn','summary.json'] for p in [folder/name]})
            results.append(result);print(result['case'],result['passed'],flush=True)
        current,current_models=candidate(layout,reference,manifest)
        if current!=full or current_models!=models or digest(Path(__file__))!=identity['producer_sha256'] or provenance()!=identity['simulator_provenance']:
            raise ValueError('Benchmark inputs or producer changed')
        passed=all(r['passed'] for r in results)
        atomic(root/'summary.json',dict(passed=passed,qualified_phy=False,eligible_for_fresh_native_qualification=passed,
            manifest_sha256=digest(root/'manifest.json'),results=results,
            scope='Two native SS monitor fixtures only; complete electrical and stability qualification must run on the new exact network'))
        atomic(root/'state.json',dict(status='completed' if passed else 'requires_diagnosis'))
        print(root/'summary.json',flush=True);return 0 if passed else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);p.add_argument('--reference',required=True,type=Path)
    a=p.parse_args();return run(a.layout,a.reference)


if __name__=='__main__':raise SystemExit(main())
