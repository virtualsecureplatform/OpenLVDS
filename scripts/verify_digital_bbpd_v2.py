#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent terminal-only edge-sampler pilot remeasurement."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_digital_bbpd_v2 as pilot
import verify_digital_clocking_v2 as reader

ROOT=pilot.ROOT
h=pilot.base

@contextmanager
def profile():
    previous=reader.MODULES.copy()
    reader.MODULES['digital_bbpd_v2']=pilot
    try:
        with pilot.profile():yield
    finally:reader.MODULES.clear();reader.MODULES.update(previous)


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    curves=[]
    keys=sorted({(r['task']['spec']['drive'],r['task']['spec']['swap'],r['task']['spec']['reference_slew_ps'],r['task']['spec']['feedback_slew_ps']) for r in rows})
    for key in keys:
        selected=sorted([r for r in rows if tuple(r['task']['spec'][n] for n in ['drive','swap','reference_slew_ps','feedback_slew_ps'])==key],
            key=lambda r:r['task']['spec']['offset_ps'])
        signs=[r for r in selected if r['task']['spec']['offset_ps']!=0]
        passed=all(r['error'] is None and r['result']['correct_sign_fraction']==1 for r in signs)
        curves.append(dict(drive=key[0],swap=key[1],reference_slew_ps=key[2],feedback_slew_ps=key[3],
            source_sign_screen_passed=bool(passed),points=[dict(offset_ps=r['task']['spec']['offset_ps'],error=r['error'],result=r['result']) for r in selected]))
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=h.sha(out/'manifest.json'),
        summary_sha256=h.sha(out/'summary.json'),consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/bbpd_v2_verification'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    result=dict(identity=identity,curves=curves,witness_files=files,qualified_phy=False,detector_admitted=False,
        scope='Twelve-vote source pilot only; zero bracket, complete epoch protocol, metastability/CDC and all-PVT physical qualification remain required')
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior detector receipt changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
