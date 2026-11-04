#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure quarter-range and stress for compound drive pilots."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_rc_drive_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
h=source.h


@contextmanager
def profile():
    previous=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_rc_drive_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=measure


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    if len(rows)!=3 or {r['task']['spec']['variant'] for r in rows}!=set(source.VARIANTS):
        raise ValueError('Incomplete compound-drive coverage')
    candidates=[]
    for row in rows:
        d=row['result']
        candidates.append(dict(variant=row['task']['spec']['variant'],error=row['error'],result=d,
            source_range_and_stress_passed=bool(row['error'] is None and d['custom_mos_stress_passed'] and d['hybrid_min_below_fast_quarter'])))
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=h.sha(out/'manifest.json'),summary_sha256=h.sha(out/'summary.json'),
        consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_rc_drive_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    body=json.dumps(dict(identity=identity,candidates=candidates,witness_files=files,qualified_phy=False,legal_code_table_admitted=False,
        scope='Independent compound-source-gate/exact-unit-RC diagnostic only; no compound physical, bank, PVT or PHY admission'),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior compound-drive proof changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
