#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Host resource handoff: complete spec screen, then all sixty component cases."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID,ExecStart'],check=True,capture_output=True,text=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def prepare(screen,unit):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_spec_screen'):raise ValueError('Use specification screen')
    relative=str(screen.relative_to(ROOT));live=owner(unit)
    if live.get('MainPID','0')=='0' or live.get('ActiveState')!='active' or 'scripts/receiver_spec_screen.py run '+relative not in live.get('ExecStart',''):
        raise ValueError('Require exact live specification producer')
    paths=[screen/'manifest.json']+[ROOT/'scripts'/n for n in ['continue_receiver_spec_components.py','qualify_receiver_spec.py','receiver_spec_screen.py','env.sh']]
    identity=dict(screen=relative,unit=unit,owner=live,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='No outer SPICE lease. Only all-33 passing specification evidence may admit original sixty RX component cases. No release or coupled-link promotion.')
    out=ROOT/'build/diagnostics/receiver_spec_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_spec_followup'):raise ValueError('Use prepared specification handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json');source=ROOT/i['screen']
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Specification handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/qualify_receiver_spec.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();return (out/(label+'.log')).read_text().strip().splitlines()[-1]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior specification handoff retained')
        while True:
            unchanged();live=owner(i['unit'])
            if live['InvocationID']!=i['owner']['InvocationID']:raise ValueError('Specification producer invocation changed')
            if live['MainPID']=='0':break
            atomic(out/'state.json',dict(status='waiting_for_specification_screen',qualified_phy=False));time.sleep(20)
        summary=source/'summary.json'
        if not summary.exists() or json.loads(summary.read_text()).get('passed') is not True:
            capture_manifest(out/'summary.json',dict(status='held_specification_screen_not_passed',qualified_phy=False,manifest_sha256=stamp))
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
        if not a.producer_unit:p.error('--producer-unit is required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
