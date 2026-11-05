#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the staged routed-bank experiment only after its exact settling proof.

Host-side coordinator: observe existing systemd owners, then use the original
container producers/gates. It never restarts solvers or changes dispatch policy.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
VERSION='matched-fine-control-to-routed-bank-followup-v2.1'
CONTEXT='weighted_routed_followup_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def atomic(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','MainPID','-p','InvocationID'],
        capture_output=True,text=True,check=True)
    result=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if set(result)!={'ActiveState','MainPID','InvocationID'}:raise OSError('Incomplete producer-owner observation')
    return result


def same_live(expected,current):
    return (current['ActiveState'] in ['active','activating'] and current['MainPID']!='0'
            and all(current[k]==expected[k] for k in ['MainPID','InvocationID']))


def receipt_for(controls,root=ROOT):
    matches=[]
    for p in sorted((root/'build/diagnostics/weighted_fine_control_verification_v4').glob('*/summary.json')):
        r=json.loads(p.read_text())
        if r.get('identity',{}).get('parent')==str(controls.relative_to(root)):matches.append(p.parent)
    if len(matches)>1:raise ValueError('Ambiguous matching fine-control receipts; retain all without selecting one')
    return matches[0] if matches else None


def disposition(state,receipt,owners,expected):
    if state is not None and state.get('status')=='fine_control_pilot_complete':
        if state.get('cases')!=4 or state.get('errors')!=0:raise ValueError('Fine-control campaign did not finish all four numerical cases')
        if receipt is not None:return 'ready_for_gate'
        if not same_live(expected['verification'],owners['verification']):raise ValueError('Fine-control verifier ended or changed before its matching receipt')
        return 'waiting_control_verification'
    if state is not None and state.get('status')!='running':raise ValueError('Fine-control producer is held or failed')
    for role in ['producer','verification']:
        if not same_live(expected[role],owners[role]):raise ValueError('Fine-control '+role+' ended or changed before completion')
    return 'waiting_physical_fine_control'


def container_args(script,*args):
    return [str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',
            'scripts/'+script,*map(str,args)]


def prepare(pilot,controls,producer_unit,verification_unit):
    for path,context in [(pilot,'weighted_routed_v2'),(controls,'weighted_fine_control_v4')]:
        if path.parent!=ROOT/'build/diagnostics'/context:raise ValueError('Require the exact staged routed/control artifact namespaces')
    pm=json.loads((pilot/'manifest.json').read_text());cm=json.loads((controls/'manifest.json').read_text())
    pi=pm['identity'];ci=cm['identity']
    for path,manifest in [(pilot,pm),(controls,cm)]:
        if path.name!=hashlib.sha256(json.dumps(manifest['identity'],sort_keys=True).encode()).hexdigest()[:16]:
            raise ValueError('Prepared artifact identity changed')
    if (pi['version']!='whole-routed-repaired-weighted-bank-sparse-native-timing-v2.1'
        or ci['version']!='isolated-root-fine-double-tg-physical-and-driver-rc-v2.3'
        or pi['components']!={k:ci[k] for k in ['clock','fine_cells','repair']}
        or len(pm['tasks'])!=2 or len(cm['tasks'])!=4):raise ValueError('Staged bank and physical control repair do not match')
    if (pilot/'state.json').exists():raise ValueError('Retain the existing routed-bank execution')
    units=dict(producer=producer_unit,verification=verification_unit)
    owners={role:owner(unit) for role,unit in units.items()}
    if not all(same_live(o,o) for o in owners.values()):raise ValueError('Require both exact live fine-control owners')
    files=[Path(__file__),ROOT/'scripts/env.sh',ROOT/'scripts/probe_weighted_routed_v2.py',ROOT/'scripts/verify_weighted_routed_v2.py',
           ROOT/'scripts/weighted_bank_control_gate_v3.py',ROOT/'scripts/verify_weighted_fine_control_v4.py']
    for path,manifest in [(pilot,pm),(controls,cm)]:
        files += [path/'manifest.json',*[path/n for n in manifest['libraries']],*[path/t['id']/'bench.cir' for t in manifest['tasks']]]
    identity=dict(version=VERSION,pilot=str(pilot.relative_to(ROOT)),controls=str(controls.relative_to(ROOT)),units=units,owners=owners,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Routed follow-up context changed')
    return m


def run(out):
    m=bound(out);i=m['identity'];pilot=ROOT/i['pilot'];controls=ROOT/i['controls']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior follow-up execution')
        try:
            while True:
                bound(out)
                # A transient observation failure is not a stopped producer.
                try:
                    observed={role:owner(unit) for role,unit in i['units'].items()}
                    state=json.loads((controls/'state.json').read_text()) if (controls/'state.json').exists() else None
                    receipt=receipt_for(controls)
                except (OSError,subprocess.CalledProcessError,json.JSONDecodeError) as e:
                    atomic(out/'state.json',dict(status='retrying_dependency_observation',error=str(e),qualified_phy=False));time.sleep(20);continue
                # Re-read the receipt after observing terminal owners, avoiding a
                # completion/publication race at the process boundary.
                if receipt is None and not same_live(i['owners']['verification'],observed['verification']):receipt=receipt_for(controls)
                status=disposition(state,receipt,observed,i['owners'])
                atomic(out/'state.json',dict(status=status,owners=observed,qualified_phy=False))
                if status=='ready_for_gate':break
                time.sleep(20)
            if (pilot/'state.json').exists():raise ValueError('Routed pilot already started; no takeover or retry')
            gate_code='import sys,json; from pathlib import Path; sys.path.insert(0,"scripts"); import probe_weighted_routed_v2 as p; out=Path(sys.argv[1]); r=Path(sys.argv[2]); m=p.bound(out); c=m["identity"]["components"]; print(json.dumps(p.control_gate.require(r,p.ROOT/c["clock"],p.ROOT/c["fine_cells"],p.ROOT/c["repair"])))'
            gate_args=container_args('unused')[:-1]+['-c',gate_code,'/work/OpenLVDS/'+i['pilot'],'/work/OpenLVDS/'+str(receipt.relative_to(ROOT))]
            with (out/'control_gate.log').open('w') as log:gate=subprocess.run(gate_args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            gate.check_returncode();bound(out)
            atomic(out/'admission.json',dict(receipt=str(receipt.relative_to(ROOT)),sha256=sha(receipt/'summary.json'),qualified_phy=False))
            atomic(out/'state.json',dict(status='running_routed_native_pilot',qualified_phy=False))
            with (out/'pilot.log').open('w') as log:
                p=subprocess.run(container_args('probe_weighted_routed_v2.py','run',i['pilot'],'--control-receipt',receipt.relative_to(ROOT)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            p.check_returncode();bound(out)
            atomic(out/'state.json',dict(status='verifying_routed_native_waveforms',qualified_phy=False))
            with (out/'verification.log').open('w') as log:
                p=subprocess.run(container_args('verify_weighted_routed_v2.py',i['pilot']),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            p.check_returncode();bound(out)
            line=(out/'verification.log').read_text().strip().splitlines()[-1];inside=Path(line)
            if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/weighted_routed_verification_v2'):
                raise ValueError('Unexpected independent routed verifier output')
            report=ROOT/inside.relative_to('/work/OpenLVDS')/'summary.json';result=json.loads(report.read_text())
            if (result['identity']['parent']!=i['pilot'] or result['all_declared_raw_waveforms_verified'] is not True):
                raise ValueError('Incomplete or unrelated routed native waveform verification')
            passed=result['assessment']['sampled_sparse_screen_passed']
            atomic(out/'summary.json',dict(report=str(report.relative_to(ROOT)),sha256=sha(report),sampled_sparse_screen_passed=passed,
                qualified_phy=False,legal_code_table_admitted=False))
            atomic(out/'state.json',dict(status='sparse_screen_passed' if passed else 'held_sparse_screen_failed',qualified_phy=False))
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--controls',type=Path);p.add_argument('--producer-unit');p.add_argument('--verification-unit');a=p.parse_args()
    if a.action=='prepare':
        if any(v is None for v in [a.controls,a.producer_unit,a.verification_unit]):p.error('Provide the exact physical control artifact and both live owners')
        print(prepare(a.artifact.resolve(),a.controls.resolve(),a.producer_unit,a.verification_unit),flush=True)
    else:run(a.artifact.resolve())
