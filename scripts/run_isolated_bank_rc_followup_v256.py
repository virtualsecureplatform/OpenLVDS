#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow the exact native physical coordinator into fresh bank RC proof."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import run_isolated_native_physical_followup_v254 as source

ROOT=source.ROOT
chain=source.chain
sha=source.sha
RC='isolated_bank_joint_rc_v255'


def require_completed(r):
    if (r.get('joint_rc_passed') is not True or r.get('isolated_bank_joint_rc_qualified') is not True
        or r.get('native_topology_verified') is not True or r.get('original_extraction_preserved') is not True
        or r.get('original_and_corrected_reductions_regenerated') is not True
        or r.get('native_parameters',{}).get('native_mos')!=1479 or r.get('native_parameters',{}).get('native_mims')!=43
        or r.get('native_parameters',{}).get('newly_characterized_junction_devices')!=0
        or r.get('all_fine_junctions',{}).get('joint_rc',{}).get('fine_mos_with_all_measured_junction_fields')!=155
        or r.get('independent_terminal_current_witness',{}).get('passed') is not True
        or set(r.get('passivity',{}))!={'original_raw','corrected_raw','corrected_reduced'}
        or any(p.get('elementwise_passive_passed') is not True for p in r.get('passivity',{}).values())
        or r.get('raw_junction_correction',{}).get('passive_records_byte_identical') is not True
        or r.get('raw_junction_correction',{}).get('all_noncapacitor_devices_and_parameters_unchanged') is not True
        or r.get('independent_witness_input',{}).get('circuit_tokens_preserved') is not True):
        raise ValueError('Routed isolated-bank RC gate failed; retain all evidence')


def ready_native(state):
    if state.get('status')!='native_physical_complete':raise ValueError('Require completed native physical coordinator')
    relative=state.get('artifacts',{}).get('native_gds','')
    if re.fullmatch(r'build/diagnostics/isolated_fine_native_gds_v253/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit native GDS artifact handoff')
    native=ROOT/relative;source.require_result(native,'native');return native


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text());info=chain.unit_info(unit);invocation=info.get('InvocationID')
    source.owner_mode(info,invocation,state.get('status')=='native_physical_complete')
    pinned=dict(state['inputs']);artifacts=dict(native_coordinator=str(parent.relative_to(ROOT)),geometry=state['artifacts']['junctions'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import qualify_isolated_bank_joint_rc_v255 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    completed=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),*[ROOT/n for n in json.loads(completed.stdout)]]
    inputs={**pinned,**{str(p.relative_to(ROOT)):sha(p) for p in files}}
    def save(status,**extra):
        tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,
            inputs=inputs,pinned_source_inputs=pinned,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');tmp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured native-to-RC continuation inputs changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()) or current['artifacts'].get('junctions')!=artifacts['geometry']:
            raise ValueError('Native coordinator source/geometry binding changed')
        return current
    def execute(action,artifact,logname,extra=()):
        unchanged();cmd=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','scripts/qualify_isolated_bank_joint_rc_v255.py',action,str(artifact.relative_to(ROOT)),*extra]
        with (out/logname).open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_native_physical')
    try:
        while True:
            current=unchanged()
            if current.get('status')=='failed':raise ValueError('Native physical coordinator failed; never restart')
            mode=source.owner_mode(chain.unit_info(unit),invocation,current.get('status')=='native_physical_complete')
            if mode=='complete':native=ready_native(current);break
            time.sleep(10)
        inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json')
        artifacts['native_gds']=str(native.relative_to(ROOT));save('preparing_joint_rc')
        printed=execute('prepare',native,'prepare.log',('--geometry',artifacts['geometry']))
        rc=chain.artifact_from_log(printed,RC)
        if rc is None:raise ValueError('Missing explicit isolated RC handoff')
        artifacts['joint_rc']=str(rc.relative_to(ROOT));save('qualifying_joint_rc');execute('run',rc,'run.log')
        if json.loads((rc/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False):raise ValueError('Isolated RC producer incomplete or failed')
        require_completed(json.loads((rc/'summary.json').read_text()))
        save('joint_rc_complete',scope='Routed native bank RC/topology/junction/passivity/Schur proof only; native transient, periodic/PVT/full-clock/PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
