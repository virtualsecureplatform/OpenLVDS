#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resource handoff from all sixty spec-admitted components to receiver RC comparison."""
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
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID,ExecStart'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def prepare(source,unit):
    if not source.is_relative_to(ROOT/'build/diagnostics/receiver_spec_verified_followup'):raise ValueError('Use verified specification component handoff')
    live=owner(unit);relative=str(source.relative_to(ROOT))
    if live.get('MainPID','0')=='0' or live.get('ActiveState')!='active' or 'scripts/continue_receiver_spec_verified.py run '+relative not in live.get('ExecStart',''):raise ValueError('Require exact live component-handoff owner')
    paths=[source/'manifest.json']+[ROOT/'scripts'/n for n in ['continue_receiver_spec_rc.py','validate_receiver_spec_rc.py','qualify_receiver_spec.py','env.sh']]
    i=dict(source=relative,unit=unit,owner=live,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='Resource handoff only: all sixty specification-admitted receiver components before original full/fast RC comparison. Scientific preparer rechecks all component/specification evidence. No outer SPICE lease or joint certificate/PHY admission.')
    out=ROOT/'build/diagnostics/receiver_spec_rc_followup'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=i,qualified_phy=False));return out


def selected_components(source,report):
    if report.get('components_passed') is not True:return None
    value=Path(report['components'])
    if value.is_absolute() or '..' in value.parts or not value.is_relative_to('build/diagnostics/receiver_components'):raise ValueError('Unexpected completed component context')
    campaign=ROOT/value;r=json.loads((campaign/'summary.json').read_text())
    if (sha(campaign/'summary.json')!=report['report_sha256'] or r.get('passed') is not True or
            r.get('required')!=60 or r.get('passed_cases')!=60 or r.get('manifest_sha256')!=sha(campaign/'manifest.json')):
        raise ValueError('Require all sixty complete, bound component cases')
    return value


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_spec_rc_followup'):raise ValueError('Use prepared receiver RC handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json');source=ROOT/i['source'];receipt=source/'summary.json'
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Receiver RC handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/validate_receiver_spec_rc.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();lines=(out/(label+'.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior RC handoff retained')
        while not receipt.exists():
            unchanged()
            if owner(i['unit'])!=i['owner']:
                if receipt.exists():continue
                raise ValueError('Exact component owner ended or changed without terminal evidence')
            atomic(out/'state.json',dict(status='waiting_for_sixty_components',qualified_phy=False));time.sleep(20)
        report=json.loads(receipt.read_text())
        if report.get('manifest_sha256')!=sha(source/'manifest.json'):raise ValueError('Component resource receipt changed')
        campaign=selected_components(source,report)
        if campaign is None:
            capture_manifest(out/'summary.json',dict(status='held_components_not_passed',manifest_sha256=stamp,qualified_phy=False))
            atomic(out/'state.json',dict(status='held_components_not_passed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='preparing_receiver_rc',qualified_phy=False))
        inside=Path(call(['prepare',str(campaign)],'prepare'))
        if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/receiver_spec_rc'):raise ValueError('Unexpected receiver RC artifact')
        relative=str(inside.relative_to('/work/OpenLVDS'))
        capture_manifest(out/'prepared.json',dict(artifact=relative,manifest_sha256=sha(ROOT/relative/'manifest.json'),qualified_phy=False))
        atomic(out/'state.json',dict(status='running_receiver_rc',artifact=relative,qualified_phy=False))
        call(['run',relative],'run');r=json.loads((ROOT/relative/'summary.json').read_text())
        passed=r.get('diagnostic_complete') is True and r.get('receiver_rc_passed') is True and r.get('manifest_sha256')==sha(ROOT/relative/'manifest.json')
        capture_manifest(out/'summary.json',dict(artifact=relative,receiver_rc_passed=passed,report_sha256=sha(ROOT/relative/'summary.json'),manifest_sha256=stamp,qualified_phy=False))
        atomic(out/'state.json',dict(status='completed_rc_handoff' if passed else 'held_rc_comparison_failed',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.producer_unit:p.error('--producer-unit required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
