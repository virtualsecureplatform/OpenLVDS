#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Wait for one existing RC producer, then run gated zero and sparse screens.

Never starts/restarts the RC producer or repeats existing timing artifacts.
This host-side coordinator records each handoff and uses the original dispatcher.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
CONTEXT='unguarded_bank_chain_v170'
RC_CONTEXT='unguarded_bank_joint_rc_v165'
ZERO_CONTEXT='unguarded_bank_joint_zero_v167'
SPARSE_CONTEXT='unguarded_bank_joint_sparse_v169'


def artifact_from_log(text,context):
    pattern=r'^/work/OpenLVDS/(build/diagnostics/'+re.escape(context)+r'/[0-9a-f]{16})$'
    matches=set(re.findall(pattern,text,re.M))
    if len(matches)>1:raise ValueError('Multiple source artifacts in one producer log; preserve ambiguity')
    return ROOT/next(iter(matches)) if matches else None


def unit_info(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','InvocationID'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)


def require_result(artifact,kind):
    state=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
    if state.get('status')!='complete' or state.get('errors',0)!=0:raise ValueError(kind+' producer incomplete or numerical error')
    if kind=='rc':ok=state.get('passed') is True and r.get('joint_rc_passed') is True
    elif kind=='zero':
        rows=r.get('rows',[])
        ok=len(rows)==1 and rows[0]['error'] is None and rows[0]['result']['joint_rc_zero_screen_passed'] is True
    elif kind=='sparse':ok=r.get('comparison',{}).get('joint_rc_sparse_feasibility_passed') is True
    else:raise ValueError('Unknown stage')
    if not ok:raise ValueError(kind+' electrical/physical gate failed; retain result')
    return r


def owner_live(info,invocation):
    if info.get('InvocationID')!=invocation:raise ValueError('Producer invocation changed; do not follow a restart')
    pid=int(info.get('MainPID','0'))
    if info.get('ActiveState') not in ('active','activating') or pid<=0:return False
    try:os.kill(pid,0)
    except ProcessLookupError:return False
    return True


def run(unit,producer_log,expected_parent,folder):
    folder.mkdir(parents=True,exist_ok=False)
    info=unit_info(unit);invocation=info.get('InvocationID')
    if not invocation:raise ValueError('Require a specific existing RC producer invocation')
    stages={};code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**extra):
        temporary=folder/'state.tmp'
        temporary.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,artifacts=stages,coordinator_sha256=code_sha256,qualified_phy=False,**extra),indent=2)+'\n')
        temporary.replace(folder/'state.json')
    state('waiting_for_existing_rc')
    try:
        while True:
            current=unit_info(unit);live=owner_live(current,invocation)
            artifact=artifact_from_log(producer_log.read_text() if producer_log.exists() else '',RC_CONTEXT)
            if artifact is not None and (artifact/'state.json').exists():
                try:s=json.loads((artifact/'state.json').read_text())
                except json.JSONDecodeError:
                    if live:time.sleep(2);continue
                    raise
                if s.get('status')=='complete':
                    require_result(artifact,'rc')
                    identity=json.loads((artifact/'manifest.json').read_text())['identity']
                    if identity['parent']!=str(expected_parent.relative_to(ROOT)):raise ValueError('RC artifact belongs to another bank')
                    stages['rc']=str(artifact.relative_to(ROOT));break
            if not live:raise ValueError('Existing RC producer terminated before passing completion; never restart it')
            time.sleep(10)
        def execute(script,action,parent,logname):
            command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/'+script,action,str(parent.relative_to(ROOT))]
            with (folder/logname).open('x') as log:
                subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            return (folder/logname).read_text()
        for kind,script,context in [('zero','probe_unguarded_bank_joint_zero_v167.py',ZERO_CONTEXT),('sparse','probe_unguarded_bank_joint_sparse_v169.py',SPARSE_CONTEXT)]:
            state('preparing_'+kind)
            printed=execute(script,'prepare',artifact,kind+'_prepare.log')
            artifact=artifact_from_log(printed,context)
            if artifact is None:raise ValueError('Missing explicit '+kind+' handoff')
            stages[kind]=str(artifact.relative_to(ROOT));state('running_'+kind)
            execute(script,'run',artifact,kind+'_run.log');require_result(artifact,kind)
        state('three_point_complete',scope='Actual zero/fine31/coarse1 screens only; boundary, periodic, PVT and PHY remain open')
    except Exception as e:
        state('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--producer-log',required=True,type=Path);p.add_argument('--bank',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.producer_unit,a.producer_log.resolve(),a.bank.resolve(),a.output.resolve())
