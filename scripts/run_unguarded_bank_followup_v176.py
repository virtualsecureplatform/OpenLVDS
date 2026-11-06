#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one passing native three-point chain with periodic or boundary checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import run_unguarded_bank_chain_v177 as chain

ROOT=chain.ROOT
RECIPES=dict(periodic=('probe_unguarded_bank_joint_periodic_v174.py','unguarded_bank_joint_periodic_v174',27,'all_current_clock_interface_cases_passed'),
             boundaries=('probe_unguarded_bank_joint_boundaries_v175.py','unguarded_bank_joint_boundaries_v175',3,'six_point_native_screen_passed'))


def source_artifact(state,bank):
    if state.get('status')!='three_point_complete':raise ValueError('Require passing native three-point chain')
    value=state.get('artifacts',{}).get('sparse','');artifact=ROOT/value
    if artifact.parent!=ROOT/'build/diagnostics'/chain.SPARSE_CONTEXT or re.fullmatch('[0-9a-f]{16}',artifact.name) is None:
        raise ValueError('Require explicit matching native sparse artifact')
    chain.require_result(artifact,'sparse')
    i=json.loads((artifact/'manifest.json').read_text())['identity']
    rc=ROOT/i['parent'];ri=json.loads((rc/'manifest.json').read_text())['identity']
    if ri['parent']!=str(bank.relative_to(ROOT)):raise ValueError('Three-point artifact belongs to another bank')
    return artifact


def require_followup(artifact,kind):
    state=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
    expected=RECIPES[kind];comparison=r.get('comparison') or {}
    if state.get('status')!='complete' or state.get('cases')!=expected[2] or state.get('errors')!=0 or comparison.get(expected[3]) is not True:
        raise ValueError(kind+' native gate failed; retain complete evidence')
    return r


def run(kind,unit,producer_state,bank,out):
    out.mkdir(parents=True,exist_ok=False);info=chain.unit_info(unit);invocation=info.get('InvocationID')
    if not invocation:raise ValueError('Require a specific existing three-point producer invocation')
    artifacts={};code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def save(status,**extra):
        temporary=out/'state.tmp';temporary.write_text(json.dumps(dict(status=status,kind=kind,producer_unit=unit,
            producer_invocation=invocation,artifacts=artifacts,coordinator_sha256=code_hash,qualified_phy=False,**extra),indent=2)+'\n');temporary.replace(out/'state.json')
    save('waiting_for_native_three_point')
    try:
        while True:
            live=chain.producer_live_or_reaped(chain.unit_info(unit),invocation)
            if producer_state.exists():
                state=json.loads(producer_state.read_text())
                if state.get('status')=='three_point_complete':
                    source=source_artifact(state,bank);artifacts['source_sparse']=str(source.relative_to(ROOT));break
                if state.get('status')=='failed':raise ValueError('Native three-point producer failed; no followup prepared')
            if not live:raise ValueError('Three-point producer terminated without passing completion')
            time.sleep(10)
        script,context,_,_=RECIPES[kind]
        def execute(action,artifact,logname):
            command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/'+script,action,str(artifact.relative_to(ROOT))]
            with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            return (out/logname).read_text()
        save('preparing_'+kind);printed=execute('prepare',source,'prepare.log');artifact=chain.artifact_from_log(printed,context)
        if artifact is None:raise ValueError('Missing explicit followup artifact handoff')
        artifacts[kind]=str(artifact.relative_to(ROOT));save('running_'+kind)
        execute('run',artifact,'run.log');require_followup(artifact,kind)
        save('complete',scope='Sampled SS40 native followup only; dense common tables, all-PVT, full clock chain and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',required=True,choices=RECIPES);p.add_argument('--producer-unit',required=True);p.add_argument('--producer-state',required=True,type=Path);p.add_argument('--bank',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.kind,a.producer_unit,a.producer_state.resolve(),a.bank.resolve(),a.output.resolve())
