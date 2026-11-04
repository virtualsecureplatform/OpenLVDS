#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently group the 30 repaired-threshold slew/order cases."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_phase_threshold_slew_v2 as source
import verify_phase_threshold_v2 as threshold

ROOT=source.ROOT
base=source.base
reader=threshold.reader


@contextmanager
def profile():
    before=reader.MODULES.copy(),base.measure
    reader.MODULES['phase_threshold_slew_v2']=source;base.measure=source.measure
    try:yield
    finally:
        modules,measure=before;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def groups(rows):
    # The original threshold grouping intentionally describes swap-0 only.
    # Keep swap orders distinct; each group must still contain all three offsets.
    return [dict(g,swap=swap) for swap in [0,1]
            for g in threshold.groups([r for r in rows if r['task']['spec']['swap']==swap])]


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    if [r['task']['spec'] for r in rows]!=source.specifications():raise ValueError('Incomplete slew/order coverage')
    grouped=groups(rows)
    if len(grouped)!=10:raise ValueError('Incomplete signed-threshold groups')
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)),
        grouping_sha256=base.sha(Path(threshold.__file__)))
    receipt=ROOT/'build/diagnostics/phase_threshold_slew_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    result=dict(identity=identity,cases=len(rows),groups=grouped,witness_files=files,
        source_threshold_and_health_passed=all(g['source_threshold_and_health_passed'] for g in grouped),
        numerical_errors=sum(r['error'] is not None for r in rows),detector_admitted=False,qualified_phy=False,
        scope='SS40 repaired-threshold slew/order source evidence; no all-PVT, route updates, physical or DLL admission')
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior slew/order proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
