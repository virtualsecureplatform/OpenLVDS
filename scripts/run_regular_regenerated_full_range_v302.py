#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Wait for exact sparse-PVT and dense jobs before full-range TX characterization."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import run_regular_regenerated_pvt_v292 as sparse
import run_regular_regenerated_dense_v295 as dense

ROOT=sparse.ROOT
chain=sparse.chain
sha=sparse.sha
CONTEXT='regular_regenerated_full_range_v301'
DONORS=(('sparse','sparse_clock_pvt_complete','pvt','regular_regenerated_pvt_v291'),
        ('dense','dense_curve_complete','dense','regular_regenerated_dense_v294'))


def ready_donors(states):
    paths=[];periodic=[]
    for name,status,field,context in DONORS:
        state=states[name]
        if state.get('status')!=status:raise ValueError('Both native donor coordinators must complete')
        relative=state.get('artifacts',{}).get(field,'')
        if re.fullmatch(r'build/diagnostics/'+context+r'/[0-9a-f]{16}',relative) is None:
            raise ValueError('Require explicit native full-range donor artifact')
        parent=state.get('artifacts',{}).get('periodic','')
        if re.fullmatch(r'build/diagnostics/regular_regenerated_joint_periodic_v288/[0-9a-f]{16}',parent) is None:
            raise ValueError('Require exact periodic donor lineage')
        periodic.append(parent);paths.append(ROOT/relative)
    if periodic[0]!=periodic[1]:raise ValueError('Sparse and dense donor lineages differ')
    sparse.require_matrix(paths[0]);dense.require_curve(paths[1]);return paths


def merge_inputs(groups):
    result={}
    for group in groups:
        for name,digest in group.items():
            if name in result and result[name]!=digest:raise ValueError('Native donor source hashes disagree')
            result[name]=digest
    return result


def run(sparse_unit,sparse_parent,dense_unit,dense_parent,out):
    out.mkdir(parents=True,exist_ok=False)
    parents=dict(sparse=sparse_parent,dense=dense_parent);units=dict(sparse=sparse_unit,dense=dense_unit)
    states={n:json.loads((p/'state.json').read_text()) for n,p in parents.items()};owners={}
    for name,status,_,_ in DONORS:
        info=chain.unit_info(units[name]);invocation=info.get('InvocationID')
        sparse.source.owner_mode(info,invocation,states[name].get('status')==status)
        owners[name]=dict(unit=units[name],invocation=invocation)
    pinned={n:dict(s['inputs']) for n,s in states.items()}
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import probe_regular_regenerated_full_range_v301 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),*[ROOT/n for n in json.loads(discovery.stdout)],ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'clocking_duty_v2_2.json']
    inputs=merge_inputs([*pinned.values(),{str(p.relative_to(ROOT)):sha(p) for p in files}])
    artifacts={n+'_coordinator':str(p.relative_to(ROOT)) for n,p in parents.items()}
    def save(status,**extra):
        temp=out/'state.tmp';temp.write_text(json.dumps(dict(status=status,owners=owners,inputs=inputs,pinned_source_inputs=pinned,
            artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');temp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured full-range continuation input changed')
        current={n:json.loads((p/'state.json').read_text()) for n,p in parents.items()}
        for name,original in pinned.items():
            if any(current[name]['inputs'].get(n)!=h for n,h in original.items()):raise ValueError('Donor coordinator source binding changed')
        return current
    def execute(action,paths,logname):
        unchanged()
        command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',
            'scripts/probe_regular_regenerated_full_range_v301.py',action,*[str(p.relative_to(ROOT)) for p in paths]]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_native_donors')
    try:
        while True:
            current=unchanged();modes=[]
            for name,status,_,_ in DONORS:
                if current[name].get('status')=='failed':raise ValueError('Native donor failed; retain evidence and never restart')
                modes.append(sparse.source.owner_mode(chain.unit_info(units[name]),owners[name]['invocation'],current[name].get('status')==status))
            if all(mode=='complete' for mode in modes):paths=ready_donors(current);break
            time.sleep(10)
        for name,parent in parents.items():inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json')
        artifacts.update(sparse=str(paths[0].relative_to(ROOT)),dense=str(paths[1].relative_to(ROOT)))
        save('preparing_full_range');printed=execute('prepare',paths,'prepare.log');artifact=chain.artifact_from_log(printed,CONTEXT)
        if artifact is None:raise ValueError('Missing explicit full-range native handoff')
        artifacts['full_range']=str(artifact.relative_to(ROOT));save('running_full_range');execute('run',[artifact],'run.log')
        save('verifying_full_range');execute('verify',[artifact],'verify.log')
        result=json.loads((artifact/'summary.json').read_text())['comparison']
        save('full_range_characterization_complete',common_sequence_found=result['common_sequence_found'],
            scope='Current 16x32 TX raw-code/PVT reference-clock characterization only; selected clocks, other dimensions, updates, RX, physical ROM and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sparse-unit',required=True);p.add_argument('--sparse-source',required=True,type=Path)
    p.add_argument('--dense-unit',required=True);p.add_argument('--dense-source',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.sparse_unit,a.sparse_source.resolve(),a.dense_unit,a.dense_source.resolve(),a.output.resolve())
