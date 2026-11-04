#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently verify signed native threshold brackets and new-load health."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_phase_threshold_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
base=source.base


@contextmanager
def profile():
    previous=reader.MODULES.copy(),base.measure
    reader.MODULES['phase_threshold_v2']=source;base.measure=source.measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def groups(rows):
    fields=['reference_slew_ps','feedback_slew_ps','positive_offset']
    keys=sorted({tuple(r['task']['spec'][n] for n in fields) for r in rows})
    result=[]
    for key in keys:
        selected=sorted([r for r in rows if tuple(r['task']['spec'][n] for n in fields)==key],key=lambda r:r['task']['spec']['offset_ps'])
        coverage=[r['task']['spec']['offset_ps'] for r in selected]==[-20,0,20]
        good=coverage and all(r['error'] is None and r['result']['correct_sign_fraction']==1
            and r['result']['frontend_stress_passed'] and r['result']['common_mode_passed'] for r in selected)
        result.append(dict(zip(fields,key),source_threshold_and_health_passed=bool(good),
            points=[dict(offset_ps=r['task']['spec']['offset_ps'],result=r['result'],error=r['error']) for r in selected]))
    return result


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    grouped=groups(rows)
    if len(rows)!=18 or len(grouped)!=6:raise ValueError('Incomplete threshold pilot coverage')
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),groups=grouped,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),
        source_threshold_and_health_passed=all(g['source_threshold_and_health_passed'] for g in grouped),
        detector_admitted=False,qualified_phy=False,
        scope='SS40 static threshold/new-load source evidence only; no all-PVT, route update, physical or DLL admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/phase_threshold_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior threshold proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
