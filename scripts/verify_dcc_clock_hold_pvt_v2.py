#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent full-PVT clock-aware DCC remeasurement and exact witness proof."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import expand_dcc_clock_hold_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
base=source.base

@contextmanager
def profile():
    previous=reader.MODULES.copy(),base.measure
    reader.MODULES['dcc_clock_hold_pvt_v2']=source;base.measure=source.pilot.measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    passed=all(r['error'] is None and r['result']['event_integrity_passed'] and r['result']['pulse_generator_integrity_passed']
        and (r['task']['spec']['phase_error_ps']!=0 or r['result']['symmetric_timing_passed']) for r in rows)
    errors=[r['result']['mean_half_cycle_error_ps'] for r in rows if r['result'] and r['task']['spec']['phase_error_ps']==0 and r['result']['mean_half_cycle_error_ps'] is not None]
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),numerical_errors=sum(r['error'] is not None for r in rows),
        source_only=True,qualified_phy=False,consumer_sha256=base.sha(Path(__file__)),witness_files=files,
        candidates=[dict(topology=[1,'clock_hold','inv_4'],cases=len(rows),
            pvt_count=len({(r['task']['spec']['process'],r['task']['spec']['temperature']) for r in rows}),
            source_screen_passed=bool(passed),worst_balanced_half_cycle_error_ps=max(errors) if errors else None)],
        scope='Source pulse identity, reset hold and half-cycle timing only; fresh physical/native RC and startup qualification remain required')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),consumer_sha256=base.sha(Path(__file__)))
    receipt=ROOT/'build/diagnostics/dcc_clock_hold_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior clock-aware proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
