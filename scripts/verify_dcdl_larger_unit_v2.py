#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure the larger-unit hybrid at every declared pilot PVT."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_larger_unit_v2 as source
import verify_dcdl_balanced_drive_v2 as comparison

ROOT=source.ROOT
h=source.h
reader=comparison.reader


@contextmanager
def profile():
    before=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_larger_unit_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,old=before;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=old


def groups(rows):
    points=sorted({(r['task']['spec']['process'],r['task']['spec']['temperature']) for r in rows})
    return [dict(comparison.candidate([r for r in rows if (r['task']['spec']['process'],r['task']['spec']['temperature'])==(p,t)],'core2'),
                 process=p,temperature=t) for p,t in points]


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    if [r['task']['spec'] for r in rows]!=source.specifications():raise ValueError('Incomplete larger-unit pilot coverage')
    candidates=groups(rows)
    if len(candidates)!=3:raise ValueError('Missing declared PVT group')
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=h.sha(out/'manifest.json'),summary_sha256=h.sha(out/'summary.json'),
        consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)),comparison_sha256=h.sha(Path(comparison.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_larger_unit_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    body=json.dumps(dict(identity=identity,candidates=candidates,witness_files=files,
        sparse_pilot_passed=all(c['feasibility_passed'] for c in candidates),
        numerical_errors=sum(r['error'] is not None for r in rows),qualified_phy=False,legal_code_table_admitted=False,
        scope='Independent sparse source-core/exact-2x3-unit-RC pilot only; no compound-cell, full-bank, dense ROM, all-PVT or PHY admission'),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior larger-unit proof changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
