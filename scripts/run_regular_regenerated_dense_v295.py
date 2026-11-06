#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one exact native transport job into the two-coarse dense fine curve."""
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
CONTEXT='regular_regenerated_dense_v294'


def ready_pilot(state):
    if state.get('status')!='periodic_transport_screen_complete':raise ValueError('Require completed regular-pair native transport coordinator')
    relative=state.get('artifacts',{}).get('periodic','')
    if re.fullmatch(r'build/diagnostics/regular_regenerated_joint_periodic_v288/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit regular-pair periodic handoff')
    pilot=ROOT/relative;source.require_screen(pilot,'periodic')
    identity=json.loads((pilot/'manifest.json').read_text())['identity']
    if identity.get('parent')!=state.get('artifacts',{}).get('joint_rc'):raise ValueError('Native periodic transport belongs to another joint RC artifact')
    return pilot


def require_curve(artifact):
    s=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text());c=r.get('comparison') or {}
    if (s!=dict(status='complete',cases=64,consumed_cases=3,errors=0,qualified_phy=False)
        or len(r.get('rows') or [])!=61 or len(r.get('inherited_rows') or [])!=3
        or any(c.get(k) is not True for k in ('complete_64_code_coverage','complete_eight_edge_histories','all_native_points_passed','all_64_dense_codes_characterized','actual_joint_rc_retained'))):
        raise ValueError('Actual routed 64-code dense curve incomplete or failed')
    if any(c.get(k) is not False for k in ('full_coarse_range_covered','all_pvt_covered','legal_code_table_admitted','updates_qualified','whole_clock_qualified','electrical_qualification_passed','qualified_phy')):
        raise ValueError('Dense two-coarse characterization cannot admit a full table or PHY')
    rows=r['inherited_rows']+r['rows'];actual=[];intervals={}
    for row in rows:
        spec=row['spec'];v=row.get('result') or {};actual.append((spec['coarse'],spec['fine']))
        if (any(spec.get(k)!=value for k,value in dict(process='ss',temperature=40,frequency_mhz=410,duty=.5,cycles=8,stop_ns=25,input_slew_ps=100,load_ff=20).items())
            or row.get('error') is not None or any(v.get(k) is not True for k in source.source.NATIVE_FLAGS)
            or v.get('whole_bank_rc_retained') is not True
            or len(v.get('terminal_stress',[]))!=1529 or any(d.get('passed') is not True for d in v['terminal_stress'])
            or len(v.get('programming_gates',[]))!=173 or any(d.get('passed') is not True for d in v['programming_gates'])
            or not v.get('controls') or any(d.get('passed') is not True for d in v['controls'])
            or any(len(v.get('edge_delays_ps',{}).get(edge,[]))!=8 or any(not math.isfinite(x) or x<=0 for x in v['edge_delays_ps'][edge]) for edge in ('rise','fall'))):
            raise ValueError('Native dense curve lost original condition, safety or complete edge history')
        intervals[spec['coarse'],spec['fine']]={edge:dict(lo_ps=min(v['edge_delays_ps'][edge]),hi_ps=max(v['edge_delays_ps'][edge])) for edge in ('rise','fall')}
    if len(set(actual))!=64 or set(actual)!={(coarse,fine) for coarse in (0,1) for fine in range(32)}:
        raise ValueError('Native dense curve lacks unique complete fine-code coverage')
    expected=[dict(coarse=coarse,fine=fine,edges=intervals[coarse,fine]) for coarse,fine in sorted(intervals)]
    if c.get('delay_intervals')!=expected:raise ValueError('Native dense intervals do not reproduce')
    steps=[]
    for coarse in (0,1):
        for fine in range(31):
            for edge in ('rise','fall'):
                left=intervals[coarse,fine][edge];right=intervals[coarse,fine+1][edge]
                low=right['lo_ps']-left['hi_ps'];high=right['hi_ps']-left['lo_ps']
                steps.append(dict(coarse=coarse,from_fine=fine,to_fine=fine+1,edge=edge,minimum_increment_ps=low,maximum_increment_ps=high,
                    strict_monotonic_intervals_passed=low>0,maximum_20ps_gap_passed=high<=20,adjacent_interval_passed=bool(low>0 and high<=20)))
    overlap={edge:intervals[0,31][edge]['lo_ps']-intervals[1,0][edge]['hi_ps'] for edge in ('rise','fall')}
    adjacent=all(step['adjacent_interval_passed'] for step in steps)
    if (c.get('adjacent_fine_intervals')!=steps or c.get('conservative_coarse_overlap_ps')!=overlap
        or c.get('all_adjacent_fine_intervals_passed') is not adjacent
        or c.get('target_10ps_adjacent_gaps_met') is not bool(adjacent and all(step['maximum_increment_ps']<=10 for step in steps))
        or c.get('raw_adjacent_dense_feasibility_passed') is not bool(adjacent and all(v>0 for v in overlap.values()))):
        raise ValueError('Native dense gap or overlap metrics do not reproduce')
    # Raw-code reversals are retained characterization; filtering a common
    # legal sequence and all-PVT admission remain separate requirements.
    return r


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text());info=chain.unit_info(unit);invocation=info.get('InvocationID')
    source.owner_mode(info,invocation,state.get('status')=='periodic_transport_screen_complete');pinned=dict(state['inputs'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import probe_regular_regenerated_dense_v294 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),*[ROOT/n for n in json.loads(discovery.stdout)]]
    inputs={**pinned,**{str(p.relative_to(ROOT)):sha(p) for p in files}};artifacts=dict(transport_coordinator=str(parent.relative_to(ROOT)))
    def save(status,**extra):
        tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,inputs=inputs,
            pinned_source_inputs=pinned,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');tmp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured native dense continuation source changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()):raise ValueError('Transport coordinator input binding changed')
        return current
    def execute(action,artifact,logname):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/probe_regular_regenerated_dense_v294.py',action,str(artifact.relative_to(ROOT))]
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
        save('preparing_dense');printed=execute('prepare',pilot,'prepare.log');artifact=chain.artifact_from_log(printed,CONTEXT)
        if artifact is None:raise ValueError('Missing explicit regular-pair dense handoff')
        artifacts['dense']=str(artifact.relative_to(ROOT));save('running_dense');execute('run',artifact,'run.log');require_curve(artifact)
        save('dense_curve_complete',scope='Actual routed two-coarse SS40 dense fine curve only; full coarse range, common all-PVT tables, updates, joint DCC and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
