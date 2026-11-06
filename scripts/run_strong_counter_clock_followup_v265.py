#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow the exact strong-storage native pilot into the full clock matrix."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import time
import run_strong_storage_counter_followup_v235 as source

ROOT=source.ROOT
chain=source.chain
sha=source.sha
CONTEXT='strong_counter_clock_matrix_v264'


def ready_pilot(state):
    if state.get('status')!='fast_clear_counter_pilot_complete':raise ValueError('Require completed native strong-counter pilot coordinator')
    relative=state.get('artifacts',{}).get('transient','')
    if re.fullmatch(r'build/diagnostics/fast_clear_counter_shared_rc_v269/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit strong-counter native pilot handoff')
    pilot=ROOT/relative;s=json.loads((pilot/'state.json').read_text());r=json.loads((pilot/'summary.json').read_text())
    if (s!=dict(status='complete',cases=12,errors=0,qualified_phy=False) or len(r.get('rows') or [])!=12
        or (r.get('comparison') or {}).get('actual_shared_counter_timing_pilot_passed') is not True
        or any(row.get('error') is not None or (row.get('result') or {}).get('counter_feasibility_passed') is not True
               or (row.get('result') or {}).get('counter_shared_wire_rc_qualified') is not True for row in r['rows'])):
        raise ValueError('Strong-counter twelve-case native pilot incomplete or failed')
    i=json.loads((pilot/'manifest.json').read_text())['identity']
    if i.get('parent')!=state['artifacts'].get('rc'):raise ValueError('Native counter pilot belongs to another shared-RC artifact')
    return pilot


def require_matrix(artifact):
    s=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
    if (s!=dict(status='complete',cases=270,consumed_cases=12,errors=0,qualified_phy=False)
        or len(r.get('rows') or [])!=258 or len(r.get('inherited_rows') or [])!=12
        or not all((r.get('comparison') or {}).get(k) is True for k in
                   ('counter_clock_matrix_passed','complete_270_case_coverage','counter_shared_wire_rc_retained'))):
        raise ValueError('Native shared-counter clock matrix incomplete or failed')
    rows=r['inherited_rows']+r['rows'];fields=('process','temperature','mhz','duty','stop_level')
    actual=[tuple(row['task']['spec'].get(k) for k in fields) for row in rows]
    expected={(p,t,f,d,level) for p in ('tt','ff','ss','fs','sf') for t in (0,25,40)
              for f in (390,400,410) for d in (.4,.5,.6) for level in (0,1)}
    if len(set(actual))!=270 or set(actual)!=expected:raise ValueError('Native clock handoff lacks unique full matrix coverage')
    for row in rows:
        v=row.get('result') or {};margin=v.get('minimum_clock_low_voltage_margin_v')
        if (row.get('error') is not None or not all(v.get(k) is True for k in
            ('held_before_request_passed','stopped_clock_clear_and_reassert_passed','terminal_screen_passed',
             'counter_feasibility_passed','phase_arming_passed','stopped_clock_arm_clear_passed',
             'alternating_phase_order_passed','stopped_clock_intermediate_clear_passed','counter_shared_wire_rc_qualified'))
            or len(v.get('terminal_stress',[]))!=644 or any(s.get('passed') is not True for s in v['terminal_stress'])
            or not isinstance(margin,(int,float)) or not math.isfinite(margin) or margin<0):
            raise ValueError('Native clock handoff lost original timing or complete terminal coverage')
    return r


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text())
    info=chain.unit_info(unit);invocation=info.get('InvocationID')
    source.owner_mode(info,invocation,state.get('status')=='fast_clear_counter_pilot_complete')
    pinned=dict(state['inputs']);binding=dict(state['artifacts'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import probe_strong_counter_clock_matrix_v264 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json',
           *[ROOT/n for n in json.loads(discovery.stdout)]]
    inputs={**pinned,**{str(p.relative_to(ROOT)):sha(p) for p in files}}
    artifacts=dict(pilot_coordinator=str(parent.relative_to(ROOT)))
    def save(status,**extra):
        tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,
            inputs=inputs,pinned_source_inputs=pinned,source_artifact_binding=binding,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');tmp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured strong-counter clock continuation input changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()) or any(current['artifacts'].get(n)!=v for n,v in binding.items()):
            raise ValueError('Native counter coordinator source or artifact binding changed')
        return current
    def execute(action,artifact,logname):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',
            'scripts/probe_strong_counter_clock_matrix_v264.py',action,str(artifact.relative_to(ROOT))]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_native_pilot')
    try:
        while True:
            current=unchanged()
            if current.get('status')=='failed':raise ValueError('Native counter coordinator failed; preserve without restart')
            mode=source.owner_mode(chain.unit_info(unit),invocation,current.get('status')=='fast_clear_counter_pilot_complete')
            if mode=='complete':pilot=ready_pilot(current);break
            time.sleep(10)
        inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json')
        artifacts['native_pilot']=str(pilot.relative_to(ROOT));save('preparing_clock_matrix')
        printed=execute('prepare',pilot,'prepare.log');artifact=chain.artifact_from_log(printed,CONTEXT)
        if artifact is None:raise ValueError('Missing explicit native clock-matrix artifact handoff')
        artifacts['clock_matrix']=str(artifact.relative_to(ROOT));save('running_clock_matrix')
        execute('run',artifact,'run.log');require_matrix(artifact)
        save('counter_clock_matrix_complete',scope='Actual shared-counter all-PVT/frequency/duty screen only; joint DCC, whole clock, management warmup and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
