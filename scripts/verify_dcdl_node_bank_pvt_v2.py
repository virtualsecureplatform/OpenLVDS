#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure dense node-bank PVT curves and bulk-update health.

Observed repeat ranges include the first pulse and code-history differences.
They are not a quantified numerical/model uncertainty bound or an admitted ROM.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_node_bank_pvt_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
h=source.h


@contextmanager
def profile():
    previous=reader.MODULES.copy(),reader.dcdl.measure
    reader.MODULES['dcdl_node_bank_pvt_v2']=source
    def measure(folder):
        tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
        return source.measure(folder,next(t for t in tasks if t['id']==folder.name))
    reader.dcdl.measure=measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);reader.dcdl.measure=measure


def curves(rows):
    keys=sorted({(r['task']['spec']['process'],r['task']['spec']['temperature'],r['task']['spec']['coarse']) for r in rows})
    result=[]
    for process,temperature,coarse in keys:
        selected=[r for r in rows if (r['task']['spec']['process'],r['task']['spec']['temperature'],r['task']['spec']['coarse'])==(process,temperature,coarse)]
        good=all(r['error'] is None and r['result']['custom_mos_stress_passed'] for r in selected)
        measured={code:[] for code in range(32)}
        for row in selected:
            if row['result']:
                for sample in row['result']['samples']:measured[sample['code']].append(sample)
        points=[]
        for code,samples in measured.items():
            if not samples:continue
            point=dict(fine_code=code,raw_code=coarse*32+code,observations=len(samples))
            for edge in ['rise','fall']:
                values=[s[edge+'_delay_ps'] for s in samples]
                point[edge+'_observed_min_ps']=min(values);point[edge+'_observed_max_ps']=max(values)
            points.append(point)
        dense=[r for r in selected if r['task']['spec']['pattern'].startswith('dense')]
        coverage=sorted(s['code'] for r in dense if r['result'] for s in r['result']['samples'])==list(range(32))
        coverage=coverage and sum(r['task']['spec']['pattern']=='bulk' and r['error'] is None for r in selected)==1
        result.append(dict(process=process,temperature=temperature,coarse=coarse,
            complete_dense_and_bulk=coverage,source_device_stress_passed=bool(good and coverage),points=points))
    return result


def report(out):
    with profile():m,rows,files=reader.remeasure(out)
    geometry=m['identity']['node_geometry_um']
    expected=source.specifications(json.loads((ROOT/'requirements.json').read_text()),geometry)
    if [r['task']['spec'] for r in rows]!=expected:raise ValueError('Incomplete or changed node-bank PVT coverage')
    groups=curves(rows)
    return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),node_geometry_um=geometry,curves=groups,
        source_device_stress_passed=bool(groups and all(g['source_device_stress_passed'] for g in groups)),
        numerical_errors=sum(r['error'] is not None for r in rows),witness_files=files,
        integration_error_bound_ps=None,qualified_phy=False,legal_code_table_admitted=False,
        scope='Independent coarse-count-16 source curves and bulk-update stress; no physical, legal-ROM, RX-range or PHY admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=h.sha(out/'manifest.json'),summary_sha256=h.sha(out/'summary.json'),
        consumer_sha256=h.sha(Path(__file__)),reader_sha256=h.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_node_bank_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior node-bank proof changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
