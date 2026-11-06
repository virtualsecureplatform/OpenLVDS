#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Admit the repaired counter all-PVT producer only after its native pilot passes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import run_unguarded_bank_chain_v177 as chain

ROOT=chain.ROOT
SOURCE_CONTEXT='counter_native_repairs_v183'
PVT_CONTEXT='counter_native_repairs_pvt_v184'


def require_source(artifact,component):
    if artifact.parent!=ROOT/'build/diagnostics'/SOURCE_CONTEXT or re.fullmatch('[0-9a-f]{16}',artifact.name) is None:raise ValueError('Require explicit native repaired-counter pilot')
    state=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
    if state!=dict(status='complete',cases=6,errors=0,qualified_phy=False) or len(r['rows'])!=6:raise ValueError('Native six-case pilot incomplete')
    for row in r['rows']:
        d=row['result'] or {}
        if row['error'] is not None or not all(d.get(k) is True for k in ('hypothesis_point_checks_passed','storage_component_physical_rc_qualified','setter_guard_geometry_qualified')):
            raise ValueError('Native pilot or physical component gate failed')
    i=json.loads((artifact/'manifest.json').read_text())['identity']
    if i['component']!=str(component.relative_to(ROOT)):raise ValueError('Pilot belongs to another physical setter component')
    return r


def run(unit,source,component,out):
    out.mkdir(parents=True,exist_ok=False);invocation=chain.unit_info(unit).get('InvocationID')
    if not invocation:raise ValueError('Require a specific existing native pilot invocation')
    artifacts=dict(source_pilot=str(source.relative_to(ROOT)));code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def save(status,**extra):
        temporary=out/'state.tmp';temporary.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,
            artifacts=artifacts,coordinator_sha256=code_hash,qualified_phy=False,**extra),indent=2)+'\n');temporary.replace(out/'state.json')
    save('waiting_for_native_pilot')
    try:
        while True:
            live=chain.producer_live_or_reaped(chain.unit_info(unit),invocation)
            if (source/'state.json').exists():
                s=json.loads((source/'state.json').read_text())
                if s.get('status')=='complete':require_source(source,component);break
            if not live:raise ValueError('Native pilot terminated before passing completion; do not restart')
            time.sleep(10)
        script='scripts/probe_counter_native_repairs_pvt_v184.py'
        def execute(action,artifact,logname):
            command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',script,action,str(artifact.relative_to(ROOT))]
            with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            return (out/logname).read_text()
        save('preparing_pvt');printed=execute('prepare',source,'prepare.log');artifact=chain.artifact_from_log(printed,PVT_CONTEXT)
        if artifact is None:raise ValueError('Missing explicit all-PVT artifact handoff')
        artifacts['pvt']=str(artifact.relative_to(ROOT));save('running_pvt');execute('run',artifact,'run.log')
        s=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
        if s!=dict(status='complete',cases=90,consumed_cases=6,errors=0,qualified_phy=False) or not (r.get('comparison') or {}).get('component_pvt_screen_passed'):
            raise ValueError('Native counter PVT screen failed; preserve complete evidence')
        save('component_pvt_complete',scope='Native counter component-RC PVT only; shared wiring, full clock/DCC/warmup and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',required=True,type=Path);p.add_argument('--component',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.component.resolve(),a.output.resolve())
