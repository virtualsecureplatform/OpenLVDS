#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resource handoff from a bound native pilot owner to full native output checks."""
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
        raise ValueError('Require live native pilot owner or bound terminal receipt')
    target='scripts/probe_driver_compact_native.py run /work/OpenLVDS/'+relative
    if live.get('ActiveState')!='active' or target not in live.get('ExecStart',''):
        raise ValueError('Require the exact live native pilot owner')


def prepare(source,unit):
    if not source.is_relative_to(ROOT/'build/diagnostics/driver_compact_native_pilot'):
        raise ValueError('Use the compact-driver native pilot')
    m=json.loads((source/'manifest.json').read_text());i=m['identity']
    if source.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Native pilot identity changed')
    relative=str(source.relative_to(ROOT));receipt=source/'summary.json';terminal=False
    if receipt.exists():
        terminal=json.loads(receipt.read_text()).get('manifest_sha256')==sha(source/'manifest.json')
        if not terminal: raise ValueError('Native pilot receipt binding changed')
    live=owner(unit);admissible_owner(live,relative,terminal)
    paths=[source/'manifest.json']+[ROOT/'scripts'/n for n in ['continue_driver_compact_native.py',
        'qualify_driver_compact_native.py','probe_driver_compact_native.py','continue_receiver_spec_verified.py',
        'dll_campaign.py','receiver_static_diagnosis.py','env.sh']]
    identity=dict(source=relative,unit=unit,owner=live,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='Resource handoff only. Wait for the exact native pilot owner and a bound '
              'terminal receipt, require all six pilots passing, then independently '
              'remeasure them before preparing all thirty native output cases. Two '
              'individually leased P1 workers under the existing six-engine limit, '
              'no outer lease. No long-component, MOS-stress or PHY admission.')
    out=ROOT/'build/diagnostics/driver_compact_native_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_compact_native_followup'):
        raise ValueError('Use prepared compact native handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    source=ROOT/i['source'];receipt=source/'summary.json'
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or
                out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):
            raise ValueError('Compact native handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3',
                              'scripts/qualify_driver_compact_native.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged()
        lines=(out/(label+'.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists(): raise ValueError('Prior native handoff retained')
        while True:
            unchanged();live=owner(i['unit']);terminal=receipt.exists()
            if terminal:
                report=json.loads(receipt.read_text())
                if report.get('manifest_sha256')!=sha(source/'manifest.json'):
                    raise ValueError('Native pilot terminal receipt changed')
            if wait_state(live,i['owner'],terminal)=='ready':break
            atomic(out/'state.json',dict(status='waiting_for_native_output_pilot',qualified_phy=False));time.sleep(20)
        if (report.get('native_output_pilot_passed') is not True or report.get('required_cases')!=6 or
                report.get('required_pvt')!=3 or report.get('passed_pvt')!=3):
            capture_manifest(out/'summary.json',dict(status='held_native_pilot_not_passed',
                pilot_report_sha256=sha(receipt),manifest_sha256=stamp,qualified_phy=False))
            atomic(out/'state.json',dict(status='held_native_pilot_not_passed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='preparing_native_output_matrix',qualified_phy=False))
        inside=Path(call(['prepare',i['source']],'prepare'))
        if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/driver_compact_native'):
            raise ValueError('Unexpected full native artifact')
        relative=str(inside.relative_to('/work/OpenLVDS'))
        capture_manifest(out/'prepared.json',dict(artifact=relative,manifest_sha256=sha(ROOT/relative/'manifest.json'),qualified_phy=False))
        atomic(out/'state.json',dict(status='running_native_output_matrix',artifact=relative,qualified_phy=False))
        call(['run',relative],'run');result=json.loads((ROOT/relative/'summary.json').read_text())
        passed=(result.get('native_output_matrix_passed') is True and result.get('required_cases')==30 and
                result.get('required_pvt')==15 and result.get('passed_pvt')==15 and
                result.get('manifest_sha256')==sha(ROOT/relative/'manifest.json'))
        if passed: call(['verify',relative],'verify')
        capture_manifest(out/'summary.json',dict(native_output_matrix_passed=passed,artifact=relative,
            report_sha256=sha(ROOT/relative/'summary.json'),manifest_sha256=stamp,qualified_phy=False))
        atomic(out/'state.json',dict(status='completed_native_output_matrix' if passed else 'held_native_output_matrix',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.producer_unit:p.error('--producer-unit required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    else: run(a.artifact.resolve())
