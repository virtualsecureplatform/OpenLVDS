#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join retained conditional analog DC results to the full-native timing screen."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import continue_dll_slew_verified_expansion as owner_policy

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_timing_followup'
sha=owner_policy.sha
atomic=owner_policy.atomic
capture=owner_policy.capture


def prepare(parent,unit,clock_baseline):
    if not parent.is_relative_to(ROOT/'build/diagnostics/dll_analog_frontend_dc_followup'):raise ValueError('Require the retained conditional DC handoff')
    if not clock_baseline.is_relative_to(ROOT/'build/diagnostics/pfd_controls_baseline'):raise ValueError('Require the retained native clock baseline')
    live=owner_policy.owner(unit)
    if (live.get('LoadState')!='loaded' or live.get('ActiveState')!='active' or live.get('MainPID','0')=='0' or
        not live.get('InvocationID') or live.get('RemainAfterExit')!='yes' or
        'continue_dll_analog_frontend_dc.py' not in live.get('ExecStart','') or parent.name not in live['ExecStart']):
        raise ValueError('Require the original live retained analog DC invocation')
    pm=json.loads((parent/'manifest.json').read_text());files=dict(pm['identity']['files'])
    paths=[parent/'manifest.json',clock_baseline/'manifest.json',clock_baseline/'full.spice']
    paths += [ROOT/'scripts'/n for n in (Path(__file__).name,'continue_dll_slew_verified_expansion.py','probe_dll_analog_frontend_timing.py','pilot_native_slew_dll.py','probe_native_pfd_controls.py','env.sh')]
    files.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    identity=dict(parent=str(parent.relative_to(ROOT)),unit=unit,owner=live,clock_baseline=str(clock_baseline.relative_to(ROOT)),files=files,no_outer_lease=True,
                  scope='Verified conditional DC survivors to full-native analog frontend timing screen. No automatic PVT expansion, physical run or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def dc_artifact(parent):
    state=json.loads((parent/'state.json').read_text())
    if state['status'] in ('held_standard_cell_survivor','held_analog_headroom_failed'):return None
    if state['status']!='analog_dc_verified':raise ValueError('Upstream did not independently verify the analog DC grid')
    report=json.loads((parent/'summary.json').read_text());rel=Path(report['artifact'])
    if (rel.is_absolute() or '..' in rel.parts or not rel.is_relative_to('build/diagnostics/dll_analog_frontend_dc') or
        not report['dc_ready_variants'] or state['artifact']!=str(rel) or state['dc_ready_variants']!=report['dc_ready_variants'] or
        sha(ROOT/rel/'summary.json')!=report['report_sha256']):raise ValueError('Analog DC receipt changed')
    return rel


def prepared_path(text):
    path=Path(text.strip().splitlines()[-1])
    rel=path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
    if '..' in rel.parts or not rel.is_relative_to('build/diagnostics/dll_analog_frontend_timing'):raise ValueError('Unexpected analog timing artifact')
    return rel


def run(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or i['no_outer_lease'] is not True or sha(out/'manifest.json')!=stamp or
            any(sha(ROOT/n)!=h for n,h in i['files'].items())):raise ValueError('Analog timing handoff context changed')
    def invoke(action,artifact,label,extra=()):
        unchanged();p=subprocess.run(['scripts/env.sh','--ngspice','/usr/bin/python3','scripts/probe_dll_analog_frontend_timing.py',action,str(artifact),*extra],
                                    cwd=ROOT,capture_output=True,text=True)
        (out/(label+'.log')).write_text(p.stdout+p.stderr);p.check_returncode();unchanged();return p.stdout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Existing analog timing handoff retained; no retry')
        try:
            unchanged();atomic(out/'state.json',dict(status='waiting_for_analog_dc',qualified_phy=False))
            while not owner_policy.terminal(i['owner'],owner_policy.owner(i['unit'])):
                unchanged();time.sleep(15)
            unchanged();parent=ROOT/i['parent'];dc=dc_artifact(parent)
            capture(out/'dc_terminal.json',dict(state_sha256=sha(parent/'state.json'),artifact=str(dc) if dc else None,qualified_phy=False))
            if dc is None:
                atomic(out/'state.json',dict(status='held_no_analog_dc_survivor',qualified_phy=False));return
            artifact=prepared_path(invoke('prepare',dc,'prepare_timing',('--clock-baseline',i['clock_baseline'])))
            capture(out/'prepared.json',dict(artifact=str(artifact),manifest_sha256=sha(ROOT/artifact/'manifest.json')))
            atomic(out/'state.json',dict(status='screening_analog_timing',artifact=str(artifact),qualified_phy=False))
            invoke('run',artifact,'run_timing');invoke('verify',artifact,'verify_timing')
            result=json.loads((ROOT/artifact/'summary.json').read_text())
            capture(out/'summary.json',dict(artifact=str(artifact),report_sha256=sha(ROOT/artifact/'summary.json'),ranked_survivors=result['ranked_survivors'],physical_admission=False,qualified_phy=False))
            atomic(out/'state.json',dict(status='analog_timing_verified' if result['ranked_survivors'] else 'held_analog_timing_failed',
                                        artifact=str(artifact),ranked_survivors=result['ranked_survivors'],qualified_phy=False))
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--unit');p.add_argument('--clock-baseline',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.unit or not a.clock_baseline:p.error('--unit and --clock-baseline required')
        print(prepare(a.artifact.resolve(),a.unit,a.clock_baseline.resolve()),flush=True)
    else:run(a.artifact.resolve())
