#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure terminal v2 source evidence, including binary/export equality.

Independent consumer receipts never replace a producer summary. Source-cell
feasibility cannot authorize physical, detector, closed-loop or PHY release.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import probe_digital_dcc_v2 as base
import probe_digital_dcc_drive_v2 as drive
import probe_digital_dcc_output_v2 as output
import expand_digital_dcc_v2 as pvt
import probe_digital_dcdl_v2 as dcdl
import probe_digital_dcdl_smooth_v2 as smooth

ROOT=base.ROOT
MODULES={'digital_dcc_v2':base,'digital_dcc_drive_v2':drive,'digital_dcc_output_v2':output,
    'digital_dcc_pvt_v2':pvt,'digital_dcdl_v2':dcdl,'digital_dcdl_smooth_v2':smooth}
REQUIRED={'bench.cir','bench.ngspice.cir','bench.raw','bench.cir.prn','ngspice.log','console.log'}


def export_matches_raw(folder):
    names,w=base.read_raw(folder/'bench.raw')
    with (folder/'bench.cir.prn').open() as stream:
        header=stream.readline().split(); exported=np.loadtxt(stream,ndmin=2)
    if header[:2]!=['Index','TIME'] or exported.shape!=(len(w),len(header)):
        raise ValueError('Incomplete or changed export shape')
    if not np.array_equal(exported[:,0],np.arange(len(w))) or not np.array_equal(exported[:,1],w[:,names.index('time')]):
        raise ValueError('Binary/export time or row mismatch')
    for i,tag in enumerate(header[2:],2):
        raw=tag.lower().replace(':','.')
        if raw not in names or not np.array_equal(exported[:,i],w[:,names.index(raw)]):
            raise ValueError('Binary/export voltage mismatch: '+tag)
    if not np.isfinite(exported).all():raise ValueError('Nonfinite source evidence')


def remeasure(out):
    out=out.resolve()
    if out.parent.name not in MODULES or not out.is_relative_to(ROOT/'build/diagnostics'):
        raise ValueError('Require an isolated v2 source context')
    module=MODULES[out.parent.name]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=module.bound(out); state=json.loads((out/'state.json').read_text())
        if state['status']!='source_screen_complete' or state['cases']!=len(m['tasks']):
            raise ValueError('Source campaign is not terminal')
        rows=json.loads((out/'summary.json').read_text())['rows']
        if len(rows)!=len(m['tasks']) or [r['task'] for r in rows]!=m['tasks']:
            raise ValueError('Incomplete, duplicated or changed source rows')
        files={str((out/n).relative_to(ROOT)):base.sha(out/n) for n in ['manifest.json','summary.json','state.json']}
        for row in rows:
            folder=out/row['task']['id']
            if json.loads((folder/'summary.json').read_text())!=row:
                raise ValueError('Case/aggregate mismatch')
            if not {'bench.cir','ngspice.log','console.log'}<=set(row['files']):
                raise ValueError('Missing source case records')
            if any(base.sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Changed source outputs')
            if row['error'] is None:
                if not REQUIRED<=set(row['files']):raise ValueError('Missing terminal source output')
                export_matches_raw(folder)
                result=(dcdl.measure(folder) if 'dcdl' in out.parent.name else base.measure(folder,row['task']['spec']))
                if result!=row['result']:raise ValueError('Remeasured source differs')
            elif row['result'] is not None:raise ValueError('Failed source case has a result')
            files.update({str((folder/n).relative_to(ROOT)):h for n,h in row['files'].items()})
            files[str((folder/'summary.json').relative_to(ROOT))]=base.sha(folder/'summary.json')
        module.bound(out)
        return m,rows,files


def report(out):
    m,rows,files=remeasure(out)
    result=dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),
        numerical_errors=sum(r['error'] is not None for r in rows),qualified_phy=False,
        source_only=True,consumer_sha256=base.sha(Path(__file__)),witness_files=files)
    if 'dcdl' in out.parent.name:
        groups=[]
        for coarse in sorted({r['task']['spec']['coarse'] for r in rows}):
            selected=[r for r in rows if r['task']['spec']['coarse']==coarse]
            groups.append(dict(coarse=coarse,samples=[dict(fine=r['task']['spec']['fine'],result=r['result'],error=r['error']) for r in selected]))
        result.update(delay_samples=groups,legal_code_table_admitted=False,
            scope='Sparse source delay samples; dense monotonicity, all-PVT overlap and uncertainty bounds still required')
    else:
        candidates=[]
        key=lambda s:(s['buffers'],s.get('drive',1),s.get('output_cell','direct'))
        for topology in sorted({key(r['task']['spec']) for r in rows}):
            selected=[r for r in rows if key(r['task']['spec'])==topology]
            balanced=[r for r in selected if r['task']['spec']['phase_error_ps']==0]
            passed=bool(balanced) and all(r['error'] is None and r['result']['event_integrity_passed'] for r in selected)
            passed=passed and all(r['result'] and r['result']['symmetric_timing_passed'] is True for r in balanced)
            errors=[r['result']['mean_half_cycle_error_ps'] for r in balanced if r['result']]
            candidates.append(dict(topology=topology,cases=len(selected),source_screen_passed=bool(passed),
                worst_balanced_half_cycle_error_ps=max(errors) if errors else None,
                pvt_count=len({(r['task']['spec']['process'],r['task']['spec']['temperature']) for r in selected})))
        result.update(candidates=candidates,
            scope='Source-cell event integrity and half-cycle symmetry at 20 fF; no native RC, gate-load, detector, terminal-stress or PHY admission')
    return result


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),
                  summary_sha256=base.sha(out/'summary.json'),consumer_sha256=base.sha(Path(__file__)))
    receipt=ROOT/'build/diagnostics/digital_clocking_v2_verification'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:
        raise ValueError('Prior independent receipt changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
