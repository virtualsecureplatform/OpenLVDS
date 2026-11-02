#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Preserve completed scientific receipts when a transient owner is unloaded."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
import continue_receiver_spec_components as original
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def wait_state(live,expected,terminal_receipt):
    if live['MainPID']=='0':
        if terminal_receipt:return 'ready'
        raise ValueError('Producer ended without terminal scientific evidence')
    if live!=expected:raise ValueError('Live prerequisite owner changed')
    return 'waiting'


def prepare(source,unit):
    base=original.prepare(source,unit)
    i=copy.deepcopy(json.loads((base/'manifest.json').read_text())['identity'])
    i['inputs'][str((ROOT/'scripts/continue_receiver_spec_verified.py').relative_to(ROOT))]=sha(Path(__file__))
    i['inputs'][str((base/'manifest.json').relative_to(ROOT))]=sha(base/'manifest.json')
    i['terminal_receipt_policy']='An inactive/unloaded transient owner is acceptable only with complete bound scientific evidence; the adapter remeasures all 33 cases before component admission.'
    out=ROOT/'build/diagnostics/receiver_spec_verified_followup'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=i,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_spec_verified_followup'):raise ValueError('Use verified specification handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json');source=ROOT/i['screen']
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Verified handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/qualify_receiver_spec.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();return (out/(label+'.log')).read_text().strip().splitlines()[-1]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior verified handoff retained')
        while True:
            unchanged();summary=source/'summary.json';terminal=False
            if summary.exists():
                report=json.loads(summary.read_text())
                if report.get('manifest_sha256')!=sha(source/'manifest.json'):raise ValueError('Prerequisite terminal receipt changed')
                terminal=True
            live=original.owner(i['unit'])
            if wait_state(live,i['owner'],terminal)=='ready':break
            atomic(out/'state.json',dict(status='waiting_for_specification_screen',qualified_phy=False));time.sleep(20)
        if report.get('passed') is not True:
            capture_manifest(out/'summary.json',dict(status='held_specification_screen_not_passed',manifest_sha256=stamp,qualified_phy=False))
            atomic(out/'state.json',dict(status='held_for_diagnosis',qualified_phy=False));return
        atomic(out/'state.json',dict(status='preparing_original_components',qualified_phy=False))
        inside=Path(call(['prepare',i['screen']],'prepare'))
        if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/receiver_components'):raise ValueError('Unexpected component artifact')
        relative=str(inside.relative_to('/work/OpenLVDS'))
        capture_manifest(out/'prepared.json',dict(components=relative,manifest_sha256=sha(ROOT/relative/'manifest.json'),qualified_phy=False))
        atomic(out/'state.json',dict(status='running_original_components',artifact=relative,qualified_phy=False))
        call(['run',relative,'--jobs','2'],'run');result=json.loads((ROOT/relative/'summary.json').read_text())
        passed=result.get('passed') is True and result.get('required')==60 and result.get('passed_cases')==60
        capture_manifest(out/'summary.json',dict(components=relative,components_passed=passed,report_sha256=sha(ROOT/relative/'summary.json'),manifest_sha256=stamp,qualified_phy=False))
        atomic(out/'state.json',dict(status='completed' if passed else 'held_for_diagnosis',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.producer_unit:p.error('--producer-unit required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
