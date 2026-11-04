#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently retain the matched-slew threshold base-load repair evidence."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_phase_threshold_load_v2 as source
import verify_phase_threshold_v2 as pilot

ROOT=source.ROOT
base=source.base
reader=pilot.reader


@contextmanager
def profile():
    previous=reader.MODULES.copy(),base.measure
    reader.MODULES['phase_threshold_load_v2']=source;base.measure=source.measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    grouped=pilot.groups(rows)
    if len(rows)!=6 or len(grouped)!=2:raise ValueError('Incomplete threshold load-repair coverage')
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),groups=grouped,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),
        source_threshold_and_health_passed=all(g['source_threshold_and_health_passed'] for g in grouped),
        detector_admitted=False,qualified_phy=False,
        scope='Matched-slew SS40 source load repair only; no unequal-slew, all-PVT, route-update, physical or DLL admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/phase_threshold_load_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior load-repair proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
