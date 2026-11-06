#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow qualified isolated RC into native zero, overlap and clock matrix gates."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import run_isolated_bank_rc_followup_v256 as source

ROOT=source.ROOT
chain=source.chain
sha=source.sha
owner_mode=source.source.owner_mode
RC='isolated_bank_joint_rc_v255'
ZERO='isolated_bank_joint_zero_v258'
SPARSE='isolated_bank_joint_sparse_v260'
PERIODIC='isolated_bank_joint_periodic_v261'


def ready_rc(state):
    if state.get('status')!='joint_rc_complete':raise ValueError('Require completed isolated RC coordinator')
    relative=state.get('artifacts',{}).get('joint_rc','')
    if re.fullmatch(r'build/diagnostics/isolated_bank_joint_rc_v255/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit isolated RC artifact handoff')
    rc=ROOT/relative
    if json.loads((rc/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False):raise ValueError('Isolated RC is not complete and passing')
    source.require_completed(json.loads((rc/'summary.json').read_text()));return rc


def require_screen(artifact,stage):
    state=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text());rows=r.get('rows') or []
    expected={'zero':dict(status='complete',cases=1,errors=0,qualified_phy=False),
        'sparse':dict(status='complete',cases=2,consumed_zero_cases=1,errors=0,qualified_phy=False),
        'periodic':dict(status='complete',cases=27,errors=0,qualified_phy=False)}
    if stage not in expected or state!=expected[stage] or len(rows)!=expected[stage]['cases']:
        raise ValueError('Isolated native transport stage incomplete')
    for row in rows:
        result=row.get('result') or {}
        if (row.get('error') is not None or len(result.get('terminal_stress',[]))!=1479 or len(result.get('programming_gates',[]))!=173
            or result.get('terminal_screen_passed') is not True or result.get('control_settling_passed') is not True
            or result.get('whole_bank_rc_retained') is not True):raise ValueError('Native device/gate/safety coverage failed')
    if stage=='zero':
        ok=rows[0]['result'].get('joint_rc_zero_screen_passed') is True and rows[0]['result'].get('output_slew_domain_passed') is True
    else:
        c=r.get('comparison') or {};overlap=c.get('conservative_coarse_overlap_ps') or {}
        common=set(overlap)=={'rise','fall'} and all(v is not None and v>0 for v in overlap.values())
        if stage=='sparse':ok=common and c.get('joint_rc_sparse_feasibility_passed') is True and c.get('complete_zero_trace_consumed') is True and c.get('whole_bank_rc_retained') is True
        else:ok=(common and c.get('all_periodic_transport_cases_passed') is True and c.get('all_current_clock_interface_cases_passed') is True
            and c.get('complete_native_edge_histories') is True and c.get('actual_joint_rc_retained') is True)
    if not ok:raise ValueError('Isolated native transport gate failed; retain all results')
    return r


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text());info=chain.unit_info(unit);invocation=info.get('InvocationID')
    owner_mode(info,invocation,state.get('status')=='joint_rc_complete');pinned=dict(state['inputs'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import probe_isolated_bank_joint_periodic_v261 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),*[ROOT/n for n in json.loads(discovery.stdout)]]
    inputs={**pinned,**{str(p.relative_to(ROOT)):sha(p) for p in files}};artifacts=dict(rc_coordinator=str(parent.relative_to(ROOT)))
    def save(status,**extra):
        temp=out/'state.tmp';temp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,inputs=inputs,
            pinned_source_inputs=pinned,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');temp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured native transport continuation input changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()):raise ValueError('Qualified RC coordinator source binding changed')
        return current
    def execute(script,action,artifact,logname):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/'+script,action,str(artifact.relative_to(ROOT))]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_joint_rc')
    try:
        while True:
            current=unchanged()
            if current.get('status')=='failed':raise ValueError('RC coordinator failed; never restart')
            mode=owner_mode(chain.unit_info(unit),invocation,current.get('status')=='joint_rc_complete')
            if mode=='complete':rc=ready_rc(current);break
            time.sleep(10)
        inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json');artifacts['joint_rc']=str(rc.relative_to(ROOT));previous=rc
        stages=[('zero',ZERO,'probe_isolated_bank_joint_zero_v258.py'),('sparse',SPARSE,'probe_isolated_bank_joint_sparse_v260.py'),
                ('periodic',PERIODIC,'probe_isolated_bank_joint_periodic_v261.py')]
        for stage,context,script in stages:
            save('preparing_'+stage);printed=execute(script,'prepare',previous,stage+'_prepare.log');artifact=chain.artifact_from_log(printed,context)
            if artifact is None:raise ValueError('Missing explicit '+stage+' native artifact handoff')
            artifacts[stage]=str(artifact.relative_to(ROOT));save('running_'+stage);execute(script,'run',artifact,stage+'_run.log');require_screen(artifact,stage);previous=artifact
        save('periodic_transport_screen_complete',scope='Qualified routed native bank zero/overlap/27-case frequency-duty screen only; dense/update/all-PVT/DCC/full-clock/PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
