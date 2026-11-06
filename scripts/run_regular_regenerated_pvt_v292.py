#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one exact routed regular-pair transport job into the 15-PVT screen."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import time
import run_regular_regenerated_transport_v289 as source

ROOT=source.ROOT
chain=source.chain
sha=source.sha
CONTEXT='regular_regenerated_pvt_v291'


def ready_pilot(state):
    if state.get('status')!='periodic_transport_screen_complete':raise ValueError('Require completed regular-pair native transport coordinator')
    relative=state.get('artifacts',{}).get('periodic','')
    if re.fullmatch(r'build/diagnostics/regular_regenerated_joint_periodic_v288/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit regular-pair periodic handoff')
    pilot=ROOT/relative;source.require_screen(pilot,'periodic')
    identity=json.loads((pilot/'manifest.json').read_text())['identity']
    if identity.get('parent')!=state.get('artifacts',{}).get('joint_rc'):raise ValueError('Native periodic transport belongs to another joint RC artifact')
    return pilot


def require_matrix(artifact):
    s=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text());c=r.get('comparison') or {}
    if (s!=dict(status='complete',cases=405,consumed_cases=27,errors=0,qualified_phy=False)
        or len(r.get('rows') or [])!=378 or len(r.get('inherited_rows') or [])!=27
        or any(c.get(k) is not True for k in ('complete_405_case_coverage','all_fifteen_pvt_conditions_present','sparse_clock_pvt_matrix_passed','actual_joint_rc_retained'))):
        raise ValueError('Actual routed 405-case PVT matrix incomplete or failed')
    rows=r['inherited_rows']+r['rows'];fields=('process','temperature','frequency_mhz','duty','coarse','fine')
    actual=[tuple(row['spec'].get(k) for k in fields) for row in rows]
    expected={(p,t,f,d,coarse,fine) for p in ('tt','ff','ss','fs','sf') for t in (0,25,40)
        for f in (390,400,410) for d in (.4,.5,.6) for coarse,fine in ((0,0),(0,31),(1,0))}
    if len(set(actual))!=405 or set(actual)!=expected:raise ValueError('Native PVT matrix lacks unique full condition coverage')
    for row in rows:
        v=row.get('result') or {}
        if (row.get('error') is not None or any(v.get(k) is not True for k in source.source.NATIVE_FLAGS)
            or v.get('whole_bank_rc_retained') is not True
            or len(v.get('terminal_stress',[]))!=1529 or any(d.get('passed') is not True for d in v['terminal_stress'])
            or len(v.get('programming_gates',[]))!=173 or any(d.get('passed') is not True for d in v['programming_gates'])
            or not v.get('controls') or any(d.get('passed') is not True for d in v['controls'])
            or any(len(v.get('edge_delays_ps',{}).get(edge,[]))!=8 or any(not math.isfinite(x) or x<=0 for x in v['edge_delays_ps'][edge]) for edge in ('rise','fall'))):
            raise ValueError('Native PVT matrix lost complete native safety or edge history')
    groups=[]
    for process in ('tt','ff','ss','fs','sf'):
        for temperature in (0,25,40):
            group=[row for row in rows if (row['spec']['process'],row['spec']['temperature'])==(process,temperature)]
            by={code:[row['result'] for row in group if (row['spec']['coarse'],row['spec']['fine'])==code] for code in ((0,0),(0,31),(1,0))}
            overlap={edge:min(x for v in by[0,31] for x in v['edge_delays_ps'][edge])-max(x for v in by[1,0] for x in v['edge_delays_ps'][edge]) for edge in ('rise','fall')}
            progression=all(min(x for v in by[code] for x in v['edge_delays_ps'][edge])>max(x for v in by[0,0] for x in v['edge_delays_ps'][edge]) for code in ((0,31),(1,0)) for edge in ('rise','fall'))
            if not progression or any(not math.isfinite(x) or x<=0 for x in overlap.values()):raise ValueError('Native PVT overlap or progression failed')
            groups.append(dict(process=process,temperature=temperature,cases=27,all_native_points_passed=True,conservative_coarse_overlap_ps=overlap,
                positive_progress_from_zero=True,sparse_clock_pvt_point_passed=True))
    if c.get('pvt_points')!=groups:raise ValueError('Native PVT group metrics do not reproduce')
    return r


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text());info=chain.unit_info(unit);invocation=info.get('InvocationID')
    source.owner_mode(info,invocation,state.get('status')=='periodic_transport_screen_complete');pinned=dict(state['inputs'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import probe_regular_regenerated_pvt_v291 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),*[ROOT/n for n in json.loads(discovery.stdout)]]
    inputs={**pinned,**{str(p.relative_to(ROOT)):sha(p) for p in files}};artifacts=dict(transport_coordinator=str(parent.relative_to(ROOT)))
    def save(status,**extra):
        tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,inputs=inputs,
            pinned_source_inputs=pinned,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');tmp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured native PVT continuation source changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()):raise ValueError('Transport coordinator input binding changed')
        return current
    def execute(action,artifact,logname):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/probe_regular_regenerated_pvt_v291.py',action,str(artifact.relative_to(ROOT))]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_native_transport')
    try:
        while True:
            current=unchanged()
            if current.get('status')=='failed':raise ValueError('Native transport failed; retain all evidence and never restart')
            mode=source.owner_mode(chain.unit_info(unit),invocation,current.get('status')=='periodic_transport_screen_complete')
            if mode=='complete':pilot=ready_pilot(current);break
            time.sleep(10)
        inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json');artifacts['periodic']=str(pilot.relative_to(ROOT))
        save('preparing_pvt');printed=execute('prepare',pilot,'prepare.log');artifact=chain.artifact_from_log(printed,CONTEXT)
        if artifact is None:raise ValueError('Missing explicit regular-pair PVT handoff')
        artifacts['pvt']=str(artifact.relative_to(ROOT));save('running_pvt');execute('run',artifact,'run.log');require_matrix(artifact)
        save('sparse_clock_pvt_complete',scope='Actual routed sparse-code clock PVT only; dense/common tables, updates, joint DCC, full clock and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
