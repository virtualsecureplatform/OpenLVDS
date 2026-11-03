#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Start the conditional analog DC grid only after the retained bounded screen.

Waits on the original invocation without a simulator lease. Scientific
verification, not a service exit alone, decides whether fallback is allowed.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import continue_dll_slew_verified_expansion as owner_policy

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_dc_followup'
sha=owner_policy.sha
atomic=owner_policy.atomic
capture=owner_policy.capture


def prepare(parent,unit):
    if not parent.is_relative_to(ROOT/'build/diagnostics/dll_slew_screen'):raise ValueError('Require the original bounded standard-cell screen')
    live=owner_policy.owner(unit)
    if (live.get('LoadState')!='loaded' or live.get('ActiveState')!='active' or live.get('MainPID','0')=='0' or
        not live.get('InvocationID') or live.get('RemainAfterExit')!='yes' or
        'screen_dll_slew_frontends.py' not in live.get('ExecStart','') or parent.name not in live['ExecStart']):
        raise ValueError('Require the original live retained screen invocation')
    paths=[parent/'manifest.json']+[ROOT/'scripts'/n for n in (Path(__file__).name,'continue_dll_slew_verified_expansion.py',
          'probe_dll_analog_frontend_dc.py','dll_analog_frontend.py','expand_dll_slew_frontends.py','screen_dll_slew_frontends.py','env.sh')]
    identity=dict(parent=str(parent.relative_to(ROOT)),unit=unit,owner=live,files={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  no_outer_lease=True,scope='Conditional fixed-rail analog frontend DC grid after independent no-survivor verification. No timing, physical or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def prepared_path(text):
    path=Path(text.strip().splitlines()[-1])
    rel=path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
    if '..' in rel.parts or not rel.is_relative_to('build/diagnostics/dll_analog_frontend_dc'):raise ValueError('Unexpected analog DC artifact')
    return rel


def run(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or i['no_outer_lease'] is not True or sha(out/'manifest.json')!=stamp or
            any(sha(ROOT/n)!=h for n,h in i['files'].items())):raise ValueError('Conditional analog handoff changed')
    def invoke(script,action,artifact,label):
        unchanged();p=subprocess.run(['scripts/env.sh','--ngspice','/usr/bin/python3','scripts/'+script,action,str(artifact)],
                                    cwd=ROOT,capture_output=True,text=True)
        (out/(label+'.log')).write_text(p.stdout+p.stderr);p.check_returncode();unchanged();return p.stdout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Existing analog handoff retained; no retry')
        try:
            unchanged();atomic(out/'state.json',dict(status='waiting_for_standard_screen',qualified_phy=False))
            while not owner_policy.terminal(i['owner'],owner_policy.owner(i['unit'])):
                unchanged();time.sleep(15)
            unchanged();parent=ROOT/i['parent']
            invoke('screen_dll_slew_frontends.py','verify',i['parent'],'verify_standard_screen')
            report=json.loads((parent/'summary.json').read_text())
            capture(out/'screen_terminal.json',dict(manifest_sha256=sha(parent/'manifest.json'),report_sha256=sha(parent/'summary.json'),
                                                  ranked_survivors=report['ranked_survivors'],qualified_phy=False))
            if report['ranked_survivors']:
                atomic(out/'state.json',dict(status='held_standard_cell_survivor',qualified_phy=False));return
            artifact=prepared_path(invoke('probe_dll_analog_frontend_dc.py','prepare',i['parent'],'prepare_dc'))
            capture(out/'prepared.json',dict(artifact=str(artifact),manifest_sha256=sha(ROOT/artifact/'manifest.json')))
            atomic(out/'state.json',dict(status='probing_analog_dc',artifact=str(artifact),qualified_phy=False))
            invoke('probe_dll_analog_frontend_dc.py','run',artifact,'run_dc')
            invoke('probe_dll_analog_frontend_dc.py','verify',artifact,'verify_dc')
            result=json.loads((ROOT/artifact/'summary.json').read_text())
            capture(out/'summary.json',dict(artifact=str(artifact),report_sha256=sha(ROOT/artifact/'summary.json'),dc_ready_variants=result['dc_ready_variants'],
                        timing_repair_verified=False,physical_admission=False,qualified_phy=False))
            atomic(out/'state.json',dict(status='analog_dc_verified' if result['dc_ready_variants'] else 'held_analog_headroom_failed',
                                        artifact=str(artifact),dc_ready_variants=result['dc_ready_variants'],qualified_phy=False))
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--unit')
    a=p.parse_args()
    if a.action=='prepare':
        if not a.unit:p.error('--unit required')
        print(prepare(a.artifact.resolve(),a.unit),flush=True)
    else:run(a.artifact.resolve())
