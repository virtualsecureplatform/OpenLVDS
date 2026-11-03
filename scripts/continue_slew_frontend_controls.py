#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join retained source expansion to reset/disable-qualified physical source.

Runs on the host without a simulator lease. Each control transient obtains
its own dispatcher lease; partial scientific output is never retried.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import continue_dll_slew_verified_expansion as upstream

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='slew_frontend_controls_followup'
sha=upstream.sha
atomic=upstream.atomic
capture=upstream.capture


def prepare(parent,unit,baseline):
    if not parent.is_relative_to(ROOT/'build/diagnostics'/upstream.NAMESPACE):raise ValueError('Require the retained verified-expansion handoff')
    if not baseline.is_relative_to(ROOT/'build/diagnostics/pfd_controls_baseline'):raise ValueError('Require the native reset/disable protocol baseline')
    live=upstream.owner(unit)
    if (live.get('LoadState')!='loaded' or live.get('ActiveState')!='active' or live.get('MainPID','0')=='0' or
        not live.get('InvocationID') or live.get('RemainAfterExit')!='yes' or
        'continue_dll_slew_verified_expansion.py' not in live.get('ExecStart','') or parent.name not in live['ExecStart']):
        raise ValueError('Require the original live expansion handoff with retained ownership')
    pm=json.loads((parent/'manifest.json').read_text());bm=json.loads((baseline/'manifest.json').read_text())
    files=dict(pm['identity']['files'])
    paths=[parent/'manifest.json',baseline/'manifest.json',baseline/'summary.json']
    paths += [baseline/n for n in (*bm['files'],'bench.raw','bench.cir.prn','ngspice.log','console.log')]
    paths += [ROOT/'scripts'/n for n in (Path(__file__).name,'continue_dll_slew_verified_expansion.py',
              'qualify_slew_frontend_controls.py','prepare_controlled_slew_pfd.py','prepare_slew_pfd.py','env.sh')]
    paths += [ROOT/'scripts'/n for n in bm['identity']['code']]
    files.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    identity=dict(parent=str(parent.relative_to(ROOT)),unit=unit,owner=live,baseline=str(baseline.relative_to(ROOT)),
                  files=files,no_outer_lease=True,scope='Independently verified source expansion, full source-control campaign and controlled physical-source generation. No automatic physical run or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def admitted_expansion(parent):
    state=json.loads((parent/'state.json').read_text())
    if state['status'] in ('held_analog_fallback_required','held_no_survivor'):return None
    if state['status']!='expansion_verified':raise ValueError('Upstream did not independently verify source expansion')
    r=json.loads((parent/'summary.json').read_text());artifact=Path(r['artifact'])
    if (artifact.is_absolute() or '..' in artifact.parts or not artifact.is_relative_to('build/diagnostics/dll_slew_expansion') or
        not r['ranked_survivors'] or state['ranked_survivors']!=r['ranked_survivors'] or
        sha(ROOT/artifact/'summary.json')!=r['report_sha256']):raise ValueError('Source expansion receipt changed')
    return artifact


def prepared_path(text,namespace):
    path=Path(text.strip().splitlines()[-1])
    rel=path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
    if '..' in rel.parts or not rel.is_relative_to('build/diagnostics/'+namespace):raise ValueError('Unexpected source-control artifact')
    return rel


def run(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or i['no_outer_lease'] is not True or sha(out/'manifest.json')!=stamp or
            any(sha(ROOT/n)!=h for n,h in i['files'].items())):raise ValueError('Control handoff context changed')
    def invoke(script,action,artifact,label,extra=()):
        unchanged()
        p=subprocess.run(['scripts/env.sh','--ngspice','/usr/bin/python3','scripts/'+script,action,str(artifact),*extra],
                         cwd=ROOT,capture_output=True,text=True)
        (out/(label+'.log')).write_text(p.stdout+p.stderr);p.check_returncode();unchanged();return p.stdout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Existing control handoff retained; no retry')
        try:
            unchanged();atomic(out/'state.json',dict(status='waiting_for_expansion',qualified_phy=False))
            while not upstream.terminal(i['owner'],upstream.owner(i['unit'])):
                unchanged();time.sleep(15)
            unchanged();parent=ROOT/i['parent'];expanded=admitted_expansion(parent)
            capture(out/'expansion_terminal.json',dict(state_sha256=sha(parent/'state.json'),artifact=str(expanded) if expanded else None,qualified_phy=False))
            if expanded is None:
                atomic(out/'state.json',dict(status='held_no_source_survivor',qualified_phy=False));return
            invoke('probe_native_pfd_controls.py','verify',i['baseline'],'verify_baseline')
            text=invoke('qualify_slew_frontend_controls.py','prepare',expanded,'prepare_controls',('--baseline',i['baseline']))
            controls=prepared_path(text,'slew_frontend_controls')
            capture(out/'prepared.json',dict(artifact=str(controls),manifest_sha256=sha(ROOT/controls/'manifest.json')))
            atomic(out/'state.json',dict(status='qualifying_source_controls',artifact=str(controls),qualified_phy=False))
            invoke('qualify_slew_frontend_controls.py','run',controls,'run_controls')
            invoke('qualify_slew_frontend_controls.py','verify',controls,'verify_controls')
            report=json.loads((ROOT/controls/'summary.json').read_text())
            if not report['source_controls_passed'] or not report['ranked_survivors']:
                atomic(out/'state.json',dict(status='held_source_controls_failed',artifact=str(controls),qualified_phy=False));return
            source=prepared_path(invoke('prepare_controlled_slew_pfd.py','source',controls,'prepare_source'),'slew_pfd_source')
            invoke('prepare_controlled_slew_pfd.py','bound',source,'verify_source')
            capture(out/'summary.json',dict(controls=str(controls),control_report_sha256=sha(ROOT/controls/'summary.json'),
                        source=str(source),source_manifest_sha256=sha(ROOT/source/'manifest.json'),
                        ranked_survivors=report['ranked_survivors'],physical_admission=False,qualified_phy=False))
            atomic(out/'state.json',dict(status='controlled_source_verified',source=str(source),physical_admission=False,qualified_phy=False))
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--unit');p.add_argument('--baseline',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.unit or not a.baseline:p.error('--unit and --baseline required')
        print(prepare(a.artifact.resolve(),a.unit,a.baseline.resolve()),flush=True)
    else:run(a.artifact.resolve())
