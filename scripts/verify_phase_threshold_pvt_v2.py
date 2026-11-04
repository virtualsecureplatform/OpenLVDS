#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently require every signed bracket, swap, slew and PVT point."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import expand_phase_threshold_pvt_v2 as source
import verify_phase_threshold_slew_v2 as pilot

ROOT=source.ROOT
base=source.base
reader=pilot.reader


@contextmanager
def profile():
    before=reader.MODULES.copy(),base.measure
    reader.MODULES['phase_threshold_pvt_v2']=source;base.measure=source.measure
    try:yield
    finally:
        modules,measure=before;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def groups(rows):
    points=sorted({(r['task']['spec']['process'],r['task']['spec']['temperature']) for r in rows})
    return [dict(g,process=p,temperature=t) for p,t in points
        for g in pilot.groups([r for r in rows if (r['task']['spec']['process'],r['task']['spec']['temperature'])==(p,t)])]


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    if [r['task']['spec'] for r in rows]!=source.specifications(json.loads((ROOT/'requirements.json').read_text())):
        raise ValueError('Incomplete threshold PVT coverage')
    grouped=groups(rows)
    if len(rows)!=540 or len(grouped)!=180:raise ValueError('Require all 540 native points and 180 signed brackets')
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)),grouping_sha256=base.sha(Path(pilot.__file__)))
    receipt=ROOT/'build/diagnostics/phase_threshold_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    result=dict(identity=identity,cases=len(rows),groups=grouped,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),
        source_threshold_and_health_passed=all(g['source_threshold_and_health_passed'] for g in grouped),
        detector_admitted=False,qualified_phy=False,
        scope='Fifteen-PVT static threshold/load source evidence; no route updates, physical matching, native convergence or PHY admission')
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior threshold PVT proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
