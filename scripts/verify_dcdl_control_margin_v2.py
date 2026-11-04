#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure both-direction DCDL control and stress evidence."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_control_margin_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
base=source.h


@contextmanager
def profile():
    previous=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_control_margin_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=measure


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    groups=[]
    for geometry in ['mim2x2','mim4x4']:
        selected=[r for r in rows if r['task']['spec']['restore']==geometry]
        covered=(sorted(r['task']['spec']['control_slew_ps'] for r in selected)==[20,100,200]
                 and all(r['task']['spec']['codes']==source.CODES for r in selected))
        good=covered and all(r['error'] is None and r['result']['custom_mos_stress_passed'] for r in selected)
        groups.append(dict(restore=geometry,source_control_stress_passed=bool(good),
            points=[dict(control_slew_ps=r['task']['spec']['control_slew_ps'],result=r['result'],error=r['error']) for r in selected]))
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),groups=groups,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),qualified_phy=False,legal_code_table_admitted=False,
        scope='SS40 source controls and custom MOS stress only; no all-PVT, delay-ROM or physical admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),
        summary_sha256=base.sha(out/'summary.json'),consumer_sha256=base.sha(Path(__file__)),
        reader_sha256=base.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_control_margin_verification_v2'/hashlib.sha256(
        json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:
        raise ValueError('Prior control-margin proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
