#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Admit fresh compact-counter RC and native replay after exact physical closure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import run_unguarded_bank_chain_v177 as chain

ROOT=chain.ROOT
PHYSICAL='strong_storage_counter_physical_v234'
RC='strong_storage_counter_rc_v231'
TRANSIENT='strong_storage_counter_shared_rc_v232'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require_source(source):
    if source.parent!=ROOT/'build/diagnostics'/PHYSICAL or re.fullmatch('[0-9a-f]{16}',source.name) is None:raise ValueError('Require explicit dedicated-request compact physical artifact')
    s=json.loads((source/'state.json').read_text());r=json.loads((source/'summary.json').read_text())
    if s!=dict(status='complete',passed=True,qualified_phy=False) or r.get('compact_counter_physical_passed') is not True or r.get('same_phase_logic') is not True or r.get('strong_native_storage_and_request') is not True or r.get('request_drivers')!=2:raise ValueError('Compact native physical closure failed')
    p=r['physical']
    if p.get('passed') is not True or p.get('drc_count')!='0' or p.get('lvs_passed') is not True or p.get('macro_count')!=22:raise ValueError('Compact physical inventory, DRC or LVS failed')
    if not all(p['native_master_witness'].get(k) is True for k in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified')):raise ValueError('Compact native master/placement witness failed')
    return r


def owner_mode(info,invocation,completed):
    current=info.get('InvocationID')
    if current and current!=invocation:raise ValueError('Physical producer invocation changed; never follow a restart')
    if completed:
        if current and current==invocation:return 'complete'
        if info.get('ActiveState')=='inactive' and int(info.get('MainPID','0'))==0:return 'complete'
        raise ValueError('Completed physical receipt has ambiguous producer state')
    if invocation and chain.owner_live(info,invocation):return 'live'
    raise ValueError('No matching live producer or completed physical receipt')


def run(unit,source,clock,out):
    out.mkdir(parents=True,exist_ok=False);invocation=chain.unit_info(unit).get('InvocationID')
    files=[Path(__file__),source/'manifest.json',clock/'manifest.json',*[ROOT/'scripts'/n for n in ('build_strong_storage_counter_v234.py','qualify_strong_storage_counter_rc_v231.py','probe_strong_storage_counter_shared_rc_v232.py','run_unguarded_bank_chain_v177.py')]]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in files};artifacts=dict(physical=str(source.relative_to(ROOT)),source_clock=str(clock.relative_to(ROOT)))
    def save(status,**extra):
        temp=out/'state.tmp';temp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,producer_binding='live-invocation' if invocation else 'completed-artifact',inputs=inputs,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');temp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured compact counter continuation input changed')
    def execute(script,action,artifact,logname,extra=()):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/'+script,action,str(artifact.relative_to(ROOT)),*extra]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_compact_physical')
    try:
        while True:
            unchanged();s=json.loads((source/'state.json').read_text()) if (source/'state.json').exists() else {}
            mode=owner_mode(chain.unit_info(unit),invocation,s.get('status')=='complete')
            if mode=='complete':
                require_source(source)
                for filename in ('state.json','summary.json'):inputs[str((source/filename).relative_to(ROOT))]=sha(source/filename)
                break
            if s.get('status')=='failed':raise ValueError('Strong physical producer failed; preserve artifact without restart')
            time.sleep(10)
        save('preparing_rc');printed=execute('qualify_strong_storage_counter_rc_v231.py','prepare',source,'rc_prepare.log')
        rc=chain.artifact_from_log(printed,RC)
        if rc is None:raise ValueError('Missing explicit compact RC artifact handoff')
        artifacts['rc']=str(rc.relative_to(ROOT));save('qualifying_rc');execute('qualify_strong_storage_counter_rc_v231.py','run',rc,'rc_run.log')
        r=json.loads((rc/'summary.json').read_text())
        if json.loads((rc/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or r.get('strong_storage_counter_shared_wire_rc_qualified') is not True:raise ValueError('Compact counter shared RC qualification failed')
        save('preparing_transient');printed=execute('probe_strong_storage_counter_shared_rc_v232.py','prepare',rc,'transient_prepare.log',('--source',str(clock.relative_to(ROOT))))
        transient=chain.artifact_from_log(printed,TRANSIENT)
        if transient is None:raise ValueError('Missing explicit compact native replay handoff')
        artifacts['transient']=str(transient.relative_to(ROOT));save('running_transient');execute('probe_strong_storage_counter_shared_rc_v232.py','run',transient,'transient_run.log')
        s=json.loads((transient/'state.json').read_text());r=json.loads((transient/'summary.json').read_text())
        if s!=dict(status='complete',cases=12,errors=0,qualified_phy=False) or not (r.get('comparison') or {}).get('actual_shared_counter_timing_pilot_passed'):raise ValueError('Compact counter native timing pilot failed; preserve all evidence')
        save('compact_counter_pilot_complete',scope='Compact counter shared RC and SS endpoint timing only; full clock/DCC/warmup/all-PVT/PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--clock',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    run(a.producer_unit,a.source.resolve(),a.clock.resolve(),a.output.resolve())
