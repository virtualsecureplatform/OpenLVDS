#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Queue the source PVT matrix only after a complete, bound nominal shaping pass."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from continue_receiver_spec_verified import wait_state
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID,ExecStart'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def admissible_owner(live,relative,terminal):
    if live.get('MainPID','0')=='0':
        if terminal:return
        raise ValueError('Require live shaping owner or bound terminal receipt')
    if live.get('ActiveState')!='active' or 'scripts/probe_driver_output_shape.py run '+relative not in live.get('ExecStart',''):raise ValueError('Require exact live shaping owner')


def prepare(source,unit):
    if not source.is_relative_to(ROOT/'build/diagnostics/driver_output_shape'):raise ValueError('Use the nominal shaping pilot')
    relative=str(source.relative_to(ROOT));receipt=source/'summary.json';terminal=False
    if receipt.exists():
        terminal=json.loads(receipt.read_text()).get('manifest_sha256')==sha(source/'manifest.json')
        if not terminal:raise ValueError('Nominal shaping receipt binding changed')
    live=owner(unit);admissible_owner(live,relative,terminal)
    paths=[source/'manifest.json']+[ROOT/'scripts'/n for n in ['continue_driver_shape_source.py','qualify_driver_output_shape_source.py','continue_receiver_spec_verified.py','env.sh']]
    identity=dict(source=relative,unit=unit,owner=live,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='Resource handoff only: completed passing two-polarity TT25 source pilot before all thirty source PVT cases. Scientific preparer remeasures every prerequisite. No outer SPICE lease, source selection, physical dispatch or PHY admission.')
    out=ROOT/'build/diagnostics/driver_shape_source_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_shape_source_followup'):raise ValueError('Use prepared shaping-source handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json');source=ROOT/i['source'];receipt=source/'summary.json'
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Source PVT handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/qualify_driver_output_shape_source.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();lines=(out/(label+'.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior source PVT handoff retained')
        while True:
            unchanged();live=owner(i['unit']);terminal=receipt.exists()
            if terminal:
                report=json.loads(receipt.read_text())
                if report.get('manifest_sha256')!=sha(source/'manifest.json'):raise ValueError('Nominal shaping receipt changed')
            if wait_state(live,i['owner'],terminal)=='ready':break
            atomic(out/'state.json',dict(status='waiting_for_nominal_shaping_pilot',qualified_phy=False));time.sleep(20)
        if report.get('diagnostic_complete') is not True or report.get('source_pilot_reference_checks_passed') is not True:
            capture_manifest(out/'summary.json',dict(status='held_nominal_pilot_not_passed',manifest_sha256=stamp,qualified_phy=False));atomic(out/'state.json',dict(status='held_nominal_pilot_not_passed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='preparing_source_pvt',qualified_phy=False));inside=Path(call(['prepare',i['source']],'prepare'))
        if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/driver_shape_source'):raise ValueError('Unexpected source matrix artifact')
        relative=str(inside.relative_to('/work/OpenLVDS'));capture_manifest(out/'prepared.json',dict(artifact=relative,manifest_sha256=sha(ROOT/relative/'manifest.json'),qualified_phy=False))
        atomic(out/'state.json',dict(status='running_source_pvt',artifact=relative,qualified_phy=False));call(['run',relative,'--jobs','2'],'run');r=json.loads((ROOT/relative/'summary.json').read_text())
        passed=r.get('source_waveform_matrix_passed') is True and r.get('required_cases')==30 and r.get('required_pvt')==15 and r.get('passed_pvt')==15 and r.get('manifest_sha256')==sha(ROOT/relative/'manifest.json')
        capture_manifest(out/'summary.json',dict(source_waveform_matrix_passed=passed,artifact=relative,report_sha256=sha(ROOT/relative/'summary.json'),manifest_sha256=stamp,qualified_phy=False))
        atomic(out/'state.json',dict(status='completed_source_matrix' if passed else 'held_source_matrix_failed',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.producer_unit:p.error('--producer-unit required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
