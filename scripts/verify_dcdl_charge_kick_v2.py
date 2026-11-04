#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain delay and custom-device stress for each charge-kick repair."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_charge_kick_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
h=source.h


@contextmanager
def profile():
    previous=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_charge_kick_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=measure


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    if [r['task']['spec'] for r in rows]!=[source.specification(r) for r in source.REPAIRS]:
        raise ValueError('Incomplete or changed charge-kick repair coverage')
    candidates=[]
    for row in rows:
        result=row['result']
        candidates.append(dict(repair=row['task']['spec']['repair'],error=row['error'],result=result,
            source_stress_passed=bool(row['error'] is None and result['custom_mos_stress_passed']),
            maximum_terminal_difference_v=max((d['max_terminal_difference_v'] for d in result['custom_mos_stress']),default=None) if result else None))
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),candidates=candidates,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),qualified_phy=False,legal_code_table_admitted=False,
        scope='Independent SS40 source pulse/control stress repair evidence only; no all-PVT or physical admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=h.sha(out/'manifest.json'),
        summary_sha256=h.sha(out/'summary.json'),consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_charge_kick_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:
        raise ValueError('Prior charge-kick receipt changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
