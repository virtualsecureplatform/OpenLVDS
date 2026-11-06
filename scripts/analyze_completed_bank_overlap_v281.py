#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare complete fine/coarse histories without consuming an unfinished zero."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import analyze_isolated_stage_latency_v262 as native
from probe_digital_dcc_v2 import atomic

ROOT=native.ROOT
sha=native.sha
VERSION='completed-isolated-bank-eight-edge-fine-coarse-overlap-diagnostic-v281.1'
CONTEXT='completed_bank_overlap_v281'
POINTS={(0,31,.4),(0,31,.6),(1,0,.5)}


def compare(rows):
    if len(rows)!=3:raise ValueError('Require both duty endpoints and one complete first-coarse reference')
    specs=[r['task']['spec'] for r in rows]
    keys=[(s['coarse'],s['fine'],s['duty']) for s in specs]
    if len(set(keys))!=3 or set(keys)!=POINTS:raise ValueError('Incomplete or duplicate fine/coarse endpoint coverage')
    shared=[{k:v for k,v in s.items() if k not in ('coarse','fine','duty')} for s in specs]
    if any(s!=shared[0] for s in shared) or len({r['source_version'] for r in rows})!=1:
        raise ValueError('Completed overlap histories belong to different native conditions')
    if len({str(Path(r['case']).parent) for r in rows})!=1:raise ValueError('Completed overlap cases have different native parents')
    by=dict(zip(keys,rows));result={}
    for edge in ('rise','fall'):
        delays={key:r['decomposition'][edge]['total_delays_ps'] for key,r in by.items()}
        if any(len(v)!=8 or any(not math.isfinite(x) or x<=0 for x in v) for v in delays.values()):
            raise ValueError('Require all eight finite positive native edge delays')
        coarse=delays[1,0,.5];fine=[dict(duty=d,minimum_fine31_delay_ps=min(delays[0,31,d]),
            maximum_fine31_delay_ps=max(delays[0,31,d]),
            conservative_first_coarse_overlap_ps=min(delays[0,31,d])-max(coarse)) for d in (.4,.6)]
        result[edge]=dict(first_coarse_delay_range_ps=dict(minimum=min(coarse),maximum=max(coarse)),
            fine_endpoints=fine,conservative_overlap_ps=min(r['conservative_first_coarse_overlap_ps'] for r in fine))
    return dict(edges=result,all_completed_histories_overlap=all(v['conservative_overlap_ps']>0 for v in result.values()),
                zero_code_verified=False,complete_four_point_pilot_verified=False,all_pvt_covered=False,
                electrical_qualification_passed=False,qualified_phy=False)


def run(cases):
    if len(cases)!=3 or len(set(cases))!=3:raise ValueError('Require three explicit unique completed cases')
    rows=[native.analyze(p) for p in cases];comparison=compare(rows)
    inputs={n:h for row in rows for n,h in row['inputs'].items()}
    paths=[Path(__file__),Path(native.__file__),Path(native.validate.__code__.co_filename),
           Path(native.crossings.__code__.co_filename),Path(atomic.__code__.co_filename)]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Completed native overlap evidence changed during analysis')
    identity=dict(version=VERSION,cases=[str(p.relative_to(ROOT)) for p in cases],inputs=inputs)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'summary.json',dict(rows=rows,comparison=comparison,analysis_completed=True,parameters_changed=False,qualified_phy=False,
        scope='Read-only complete three-point fine/coarse necessary-condition diagnosis; unfinished zero is not read, no whole pilot, new circuit, PVT, timing selection or PHY admission'))
    atomic(out/'state.json',dict(status='complete',analysis_completed=True,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',nargs=3,type=Path);a=p.parse_args()
    print(run([p.resolve() for p in a.cases]),flush=True)
