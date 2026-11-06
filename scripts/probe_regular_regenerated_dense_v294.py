#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure all 32 fine codes at two coarse selections on the actual routed bank."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import probe_regular_regenerated_pvt_v291 as checked
source=checked.source
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from run_regular_regenerated_physical_v284 import NATIVE_FLAGS

ROOT=source.ROOT
sha=source.sha
VERSION='actual-regular-pair-routed-ss40-dense-fine-two-coarse-v294.1'
CONTEXT='regular_regenerated_dense_v294'
SCOPE='64 actual routed regular-pair SS40 fine-code points at two coarse selections, 410MHz/50% duty and all eight native pulse histories; full range, common all-PVT tables, updates and PHY remain unqualified'
point_passed=checked.point_passed


def specifications():
    checked.specifications()  # Require the unchanged approved supply/clock/PVT contract.
    return [dict(source.native.spec(),coarse=c,fine=f,frequency_mhz=410,duty=.5,cycles=8,stop_ns=25)
        for c in (0,1) for f in range(32)]


def assess(rows,matrix):
    if len(rows)!=64 or any(r.get('error') is not None or r.get('result') is None for r in rows):return None
    actual=[json.dumps(r['spec'],sort_keys=True) for r in rows]
    if matrix!=specifications() or len(set(actual))!=64 or set(actual)!={json.dumps(s,sort_keys=True) for s in matrix}:
        raise ValueError('Require all 64 unique SS40 dense fine-code conditions')
    by={(r['spec']['coarse'],r['spec']['fine']):r['result'] for r in rows}
    histories=all(len(r.get('edge_delays_ps',{}).get(edge,[]))==8
        and all(math.isfinite(v) and v>0 for v in r['edge_delays_ps'][edge]) for r in by.values() for edge in ('rise','fall'))
    intervals={code:{edge:dict(lo_ps=min(r['edge_delays_ps'][edge]),hi_ps=max(r['edge_delays_ps'][edge])) for edge in ('rise','fall')} for code,r in by.items()} if histories else {}
    steps=[]
    if histories:
        for coarse in (0,1):
            for fine in range(31):
                for edge in ('rise','fall'):
                    left=intervals[coarse,fine][edge];right=intervals[coarse,fine+1][edge]
                    low=right['lo_ps']-left['hi_ps'];high=right['hi_ps']-left['lo_ps']
                    steps.append(dict(coarse=coarse,from_fine=fine,to_fine=fine+1,edge=edge,
                        minimum_increment_ps=low,maximum_increment_ps=high,strict_monotonic_intervals_passed=low>0,
                        maximum_20ps_gap_passed=high<=20,adjacent_interval_passed=bool(low>0 and high<=20)))
    overlap={edge:intervals[0,31][edge]['lo_ps']-intervals[1,0][edge]['hi_ps'] if histories else None for edge in ('rise','fall')}
    native=all(point_passed(r) for r in by.values())
    adjacent=histories and len(steps)==124 and all(s['adjacent_interval_passed'] for s in steps)
    return dict(complete_64_code_coverage=True,complete_eight_edge_histories=histories,all_native_points_passed=native,
        all_64_dense_codes_characterized=bool(histories and native),
        delay_intervals=[dict(coarse=c,fine=f,edges=intervals[c,f]) for c,f in sorted(intervals)],
        adjacent_fine_intervals=steps,all_adjacent_fine_intervals_passed=adjacent,
        target_10ps_adjacent_gaps_met=bool(adjacent and all(s['maximum_increment_ps']<=10 for s in steps)),
        conservative_coarse_overlap_ps=overlap,
        raw_adjacent_dense_feasibility_passed=bool(native and adjacent and all(v is not None and v>0 for v in overlap.values())),
        actual_joint_rc_retained=all(r.get('whole_bank_rc_retained') is True for r in by.values()),
        full_coarse_range_covered=False,all_pvt_covered=False,legal_code_table_admitted=False,
        updates_qualified=False,whole_clock_qualified=False,electrical_qualification_passed=False,qualified_phy=False)



def fixture(out,i,s):
    text=source.fixture(out,i,s);title='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed periodic fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    m=source.bound(parent);i=m['identity'];pilot=checked.require_pilot(parent,m);matrix=specifications();rows=[r for r in pilot if r['spec'] in matrix]
    old=[r['spec'] for r in rows]
    if len({json.dumps(s,sort_keys=True) for s in old})!=3 or any(s not in matrix for s in old):raise ValueError('Inherited clock pilot coverage changed')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')]
    for row in pilot:
        case=parent/row['task']['id']
        if (row!=json.loads((case/'summary.json').read_text())
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
            or any(sha(case/n)!=h for n,h in row['files'].items())
            or source.measure(case,dict(i,spec=row['spec']))!=row['result']):
            raise ValueError('Consumed complete routed clock trace does not reproduce')
        paths += [case/'summary.json',*[case/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += [ROOT/'requirements.json',ROOT/'clocking_duty_v2_2.json']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),matrix=matrix,specs=[s for s in matrix if s not in old],
        inherited_rows=rows,inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},max_workers=2,priority=2,scope=SCOPE)
    if len(identity['specs'])!=61:raise ValueError('Require 61 new dense codes after consuming three matched periodic cases')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for k,s in enumerate(identity['specs']):
        case=out/str(k);case.mkdir();(case/'bench.cir').write_text(fixture(out,identity,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(case/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];origin=i['inherited_rows']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or source.zero.engine()!='ngspice' or source.zero.provenance()!=i['simulator'] or i['max_workers']!=2 or i['priority']!=2
        or i['matrix']!=specifications() or len(m['tasks'])!=61 or len(i['observations']['devices'])!=1529
        or sha(Path(source.native.CAD))!=i['cad']['sha256']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['parent']/'bank.spice')!=m['bank_sha256']
        or origin!=[r for r in json.loads((ROOT/i['parent']/'summary.json').read_text())['rows'] if r['spec'] in i['matrix']]
        or len(origin)!=3 or any(not point_passed(r['result']) for r in origin)
        or i['specs']!=[s for s in i['matrix'] if s not in [r['spec'] for r in origin]]):
        raise ValueError('Actual routed regular-pair dense-code context changed')
    for k,t in enumerate(m['tasks']):
        path=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(path)) or path.read_text()!=fixture(out,i,t['spec']):raise ValueError('Actual routed dense-code fixture changed')
    return m


def measure(case,i,s):return dict(source.measure(case,dict(i,spec=s)),scope=SCOPE)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial routed dense-code campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            case=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(case/'ngspice.log'),str(case/'bench.cir')],capture_output=True,text=True)
                (case/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(case,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in case.iterdir() if p.is_file()});atomic(case/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,inherited_rows=i['inherited_rows'],comparison=assess([*i['inherited_rows'],*rows],i['matrix']),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=64,consumed_cases=3,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
