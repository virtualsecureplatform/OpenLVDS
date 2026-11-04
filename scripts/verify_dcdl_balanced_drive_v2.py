#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure balanced-driver first-edge headroom and coarse/fine overlap."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_balanced_drive_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
h=source.h


@contextmanager
def profile():
    before=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_balanced_drive_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,old=before;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=old


def candidate(rows,variant):
    selected=[r for r in rows if r['task']['spec']['variant']==variant]
    if len(selected)!=2 or {r['task']['spec']['coarse'] for r in selected}!={0,1}:raise ValueError('Incomplete coarse-pair coverage')
    if any(r['error'] is not None for r in selected):
        return dict(variant=variant,feasibility_passed=False,errors=[r['error'] for r in selected])
    by_coarse={r['task']['spec']['coarse']:r['result'] for r in selected}
    def delays(coarse,code,edge):
        return [s[edge+'_delay_ps'] for s in by_coarse[coarse]['samples'] if s['code']==code]
    cold_and_repeat_max=max(delays(0,0,'rise'))
    fastest=by_coarse[0]['required_quarter_range_ps'][0]
    overlap={edge:min(delays(0,31,edge))-max(delays(1,0,edge)) for edge in ['rise','fall']}
    stress=all(r['result']['custom_mos_stress_passed'] for r in selected)
    return dict(variant=variant,maximum_coarse0_fine0_rise_ps=cold_and_repeat_max,
        fast_quarter_headroom_ps=fastest-cold_and_repeat_max,coarse_fine_overlap_ps=overlap,
        custom_mos_stress_passed=stress,
        feasibility_passed=bool(stress and cold_and_repeat_max<fastest and min(overlap.values())>0),
        results=by_coarse,
        scope='Sparse SS40 feasibility only; positive headroom is not a routing allowance or ROM admission')


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    if [r['task']['spec'] for r in rows]!=source.specifications():raise ValueError('Incomplete balanced drive coverage')
    candidates=[candidate(rows,v) for v in source.VARIANTS]
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=h.sha(out/'manifest.json'),summary_sha256=h.sha(out/'summary.json'),
        consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_balanced_drive_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    body=json.dumps(dict(identity=identity,candidates=candidates,witness_files=files,qualified_phy=False,legal_code_table_admitted=False,
        scope='Independent sparse balanced-core/exact-unit-RC evidence; no compound physical, bank, PVT or PHY admission'),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior balanced drive proof changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
