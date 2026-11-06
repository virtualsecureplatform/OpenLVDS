#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one live fine-driver pilot into the full approved clock-input matrix."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import run_unguarded_bank_chain_v177 as chain

ROOT=chain.ROOT
SOURCE_CONTEXT='discharge_isolated_fine_bank_v220'
MATRIX_CONTEXT='discharge_fine_clock_matrix_v221'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require_source(artifact):
    if artifact.parent!=ROOT/'build/diagnostics'/SOURCE_CONTEXT or re.fullmatch('[0-9a-f]{16}',artifact.name) is None:raise ValueError('Require explicit isolated fine-driver pilot artifact')
    state=json.loads((artifact/'state.json').read_text());summary=json.loads((artifact/'summary.json').read_text());m=json.loads((artifact/'manifest.json').read_text())
    if state!=dict(status='complete',cases=8,errors=0,qualified_phy=False) or len(summary['rows'])!=8 or len(m['tasks'])!=8:raise ValueError('Fine-driver pilot incomplete or numerical failure')
    for task,row in zip(m['tasks'],summary['rows']):
        if row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None or row['result'] is None:raise ValueError('Pilot native coverage changed')
    comparison=summary.get('comparison') or []
    variants=[r['variant'] for r in comparison if r.get('component_hypothesis_passed') is True]
    if len(comparison)!=2 or not variants:raise ValueError('No passing fine-driver hypothesis; retain original pilot')
    for v in variants:
        rows=[r for r in summary['rows'] if all(r['spec'][k]==v[k] for k in ('driver','fine_copies'))]
        if len(rows)!=4 or not all(r['result'].get('current_clock_interface_screen_passed') is True for r in rows):raise ValueError('Passing comparison contradicts native pilot cases')
    return variants


def run(unit,source,out):
    out.mkdir(parents=True,exist_ok=False);invocation=chain.unit_info(unit).get('InvocationID')
    if not invocation:raise ValueError('Require a specific existing fine-driver pilot invocation')
    runner=ROOT/'scripts/probe_discharge_fine_clock_matrix_v221.py';runner_hash=sha(runner)
    manifest_hash=sha(source/'manifest.json');artifacts=dict(pilot=str(source.relative_to(ROOT)));code_hash=sha(Path(__file__))
    def save(status,**extra):
        temp=out/'state.tmp';temp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,source_manifest_sha256=manifest_hash,matrix_runner_sha256=runner_hash,
            artifacts=artifacts,coordinator_sha256=code_hash,qualified_phy=False,**extra),indent=2)+'\n');temp.replace(out/'state.json')
    save('waiting_for_pilot')
    try:
        while True:
            live=chain.producer_live_or_reaped(chain.unit_info(unit),invocation)
            if sha(source/'manifest.json')!=manifest_hash or sha(runner)!=runner_hash:raise ValueError('Explicit pilot manifest changed')
            if (source/'state.json').exists() and json.loads((source/'state.json').read_text()).get('status')=='complete':
                variants=require_source(source);break
            if not live:raise ValueError('Pilot terminated without complete admission; never restart')
            time.sleep(10)
        def execute(action,artifact,logname):
            if sha(runner)!=runner_hash:raise ValueError('Captured full clock matrix runner changed')
            command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/probe_discharge_fine_clock_matrix_v221.py',action,str(artifact.relative_to(ROOT))]
            with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            return (out/logname).read_text()
        save('preparing_clock_matrix',variants=variants);printed=execute('prepare',source,'prepare.log');artifact=chain.artifact_from_log(printed,MATRIX_CONTEXT)
        if artifact is None:raise ValueError('Missing explicit clock-matrix artifact handoff')
        artifacts['clock_matrix']=str(artifact.relative_to(ROOT));save('running_clock_matrix',variants=variants);execute('run',artifact,'run.log')
        state=json.loads((artifact/'state.json').read_text());summary=json.loads((artifact/'summary.json').read_text());results=summary.get('comparison') or []
        if state!=dict(status='complete',cases=27*len(variants),consumed_cases=4*len(variants),errors=0,qualified_phy=False) or len(results)!=len(variants):raise ValueError('Full clock-matrix campaign incomplete; retain all evidence')
        passed=[r['variant'] for r in results if r.get('complete_27_case_clock_stress_screen_passed') is True]
        save('clock_matrix_complete',passing_variants=passed,scope='Native component-RC sparse frequency/duty only; dense/update/all-PVT/whole-bank RC/full-clock/PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
