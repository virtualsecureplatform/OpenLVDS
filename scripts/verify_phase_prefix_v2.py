#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Pair short/long native waveforms without weakening health or timing gates."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import probe_phase_prefix_v2 as source
import verify_digital_clocking_v2 as reader

ROOT=source.ROOT
base=source.base
LIMITS=dict(maximum_voltage_error_v=.01,maximum_edge_error_ps=.25,maximum_stress_error_v=.001)


@contextmanager
def profile():
    previous=reader.MODULES.copy(),base.measure
    reader.MODULES['phase_prefix_v2']=source;base.measure=source.measure
    try:yield
    finally:
        modules,measure=previous;reader.MODULES.clear();reader.MODULES.update(modules);base.measure=measure


def compare(long_names,long_wave,short_names,short_wave,short_settle):
    if long_names!=short_names:raise ValueError('Short/long probe coverage differs')
    lt=long_wave[:,long_names.index('time')]*1e12;st=short_wave[:,short_names.index('time')]*1e12
    delta=200000-short_settle
    if st[0]<-.01 or st[-1]+delta>lt[-1]+.01:raise ValueError('Comparison time coverage differs')
    maximum=0.;worst=None
    for i,name in enumerate(short_names):
        if not name.startswith('v('):continue
        error=float(np.max(np.abs(short_wave[:,i]-np.interp(st+delta,lt,long_wave[:,i]))))
        if error>maximum:maximum=error;worst=name
    edge_errors=[]
    for node in ['rfast','ffast','rth','fth']:
        a=long_wave[:,long_names.index('v('+node+')')];b=short_wave[:,short_names.index('v('+node+')')]
        for i in range(4):
            lm=(lt>=200000+i*10000+1500)&(lt<200000+i*10000+6000)
            sm=(st>=short_settle+i*10000+1500)&(st<short_settle+i*10000+6000)
            x=base.crossings(lt[lm],a[lm]);y=base.crossings(st[sm],b[sm])
            if len(x)!=1 or len(y)!=1:raise ValueError('Missing/extra edge in paired native data')
            edge_errors.append(dict(node=node,tag=i,error_ps=float(abs(x[0]-(y[0]+delta)))))
    return dict(maximum_voltage_error_v=maximum,worst_voltage_node=worst,
        maximum_edge_error_ps=max(d['error_ps'] for d in edge_errors),edge_errors=edge_errors)


def elapsed(folder):
    text=(folder/'ngspice.log').read_text()
    match=re.search(r'Total elapsed time \(seconds\)\s*=\s*([0-9.]+)',text)
    return float(match[1]) if match else None


def verify(out):
    with profile():m,rows,files=reader.remeasure(out)
    parent=ROOT/m['identity']['parent'];long=source.parent_source
    parent_proof=source.evidence.report(parent)
    if parent_proof['source_threshold_and_health_passed'] is not True:raise ValueError('Long source health changed')
    originals=json.loads((parent/'summary.json').read_text())['rows'];pairs=[]
    for row,old in zip(rows,originals):
        if row['task']['id']!=old['task']['id'] or dict(row['task']['spec'],settle_ps=None)!=dict(old['task']['spec'],settle_ps=None):
            raise ValueError('Short/long stimulus coverage differs')
        folder=out/row['task']['id'];original=parent/old['task']['id'];result=row['result'];baseline=old['result']
        if row['error'] is not None:
            pairs.append(dict(id=row['task']['id'],passed=False,error=row['error']));continue
        n,w=base.read_raw(original/'bench.raw');sn,sw=base.read_raw(folder/'bench.raw')
        difference=compare(n,w,sn,sw,row['task']['spec']['settle_ps'])
        stress=max(abs(a['max_terminal_difference_v']-b['max_terminal_difference_v']) for a,b in zip(result['frontend_stress'],baseline['frontend_stress']))
        health=result['correct_sign_fraction']==1 and result['votes']==baseline['votes'] and result['frontend_stress_passed'] and result['common_mode_passed']
        passed=(health and difference['maximum_voltage_error_v']<=LIMITS['maximum_voltage_error_v']
            and difference['maximum_edge_error_ps']<=LIMITS['maximum_edge_error_ps'] and stress<=LIMITS['maximum_stress_error_v'])
        pairs.append(dict(id=row['task']['id'],passed=bool(passed),health_passed=bool(health),maximum_stress_error_v=stress,
            short_elapsed_seconds=elapsed(folder),long_elapsed_seconds=elapsed(original),**difference))
        files.update({str((original/n).relative_to(ROOT)):v for n,v in old['files'].items()})
        files[str((original/'summary.json').relative_to(ROOT))]=base.sha(original/'summary.json')
    if len(rows)!=6 or len(originals)!=6:raise ValueError('Incomplete six-case native prefix comparison')
    source.bound(out)
    if any(base.sha(ROOT/n)!=v for n,v in files.items()):raise ValueError('Comparison witnesses changed')
    identity=dict(artifact=str(out.relative_to(ROOT)),manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)),limits=LIMITS)
    receipt=ROOT/'build/diagnostics/phase_prefix_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True)
    result=dict(identity=identity,cases=len(rows),pairs=pairs,equivalence_passed=all(p['passed'] for p in pairs),witness_files=files,
        qualified_phy=False,hardware_warmup_changed=False,
        scope='Native matched-slew SS40 quiescent-prefix equivalence only; no all-PVT, new load, hardware warmup or PHY admission')
    body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior prefix proof changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
