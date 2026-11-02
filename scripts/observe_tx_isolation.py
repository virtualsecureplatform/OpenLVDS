#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only raw completion evidence, independently of result-export status."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw

ROOT=Path(__file__).resolve().parents[1]
CASES=['tx_reduced','tx_raw','coupled_reduced','coupled_raw']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def trace_completion(names,wave):
    if wave.ndim!=2 or len(wave)<2 or 'time' not in names:return False
    t=wave[:,names.index('time')]
    return bool(np.isfinite(wave).all() and np.all(np.diff(t)>0) and t[0]<=1e-15 and t[-1]>=12e-9-1e-12)


def observe(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_convergence_isolation'):raise ValueError('Use TX isolation context')
    m=json.loads((out/'manifest.json').read_text());results=[];paths=[out/'manifest.json']
    if [t['id'] for t in m['tasks']]!=CASES:raise ValueError('Require four isolation conditions')
    for task in m['tasks']:
        folder=out/task['id'];summary=folder/'summary.json'
        if not summary.exists():
            results.append(dict(task=task['id'],status='pending',raw_completed_12ns=None,electrical_verdict=None));continue
        r=json.loads(summary.read_text())
        if r['manifest_sha256']!=sha(out/'manifest.json'):raise ValueError('Isolation result binding changed')
        for n,h in dict(task['files'],**r['files']).items():
            if sha(folder/n)!=h:raise ValueError('Isolation evidence changed')
        complete=False;stop=None;raw_error=None;ranges={}
        try:
            names,wave=read_raw(folder/'bench.raw');complete=trace_completion(names,wave)
            if len(wave):
                stop=float(wave[-1,names.index('time')]*1e9)
                if np.isfinite(wave).all():ranges={n:dict(min_v=float(wave[:,j].min()),max_v=float(wave[:,j].max())) for j,n in enumerate(names) if n!='time'}
        except (OSError,ValueError,IndexError) as error:raw_error=str(error)
        console=(folder/'console.log').read_text();log=(folder/'ngspice.log').read_text()
        failure=re.search(r'timestep too small[^\n]*',log,re.I)
        results.append(dict(task=task['id'],status='terminal',raw_completed_12ns=complete,raw_stop_ns=stop,voltage_ranges_v=ranges,
            export_returncode=r['returncode'],export_ground_probe_error="Missing requested ngspice vectors: {'v(0)'}" in console,
            numerical_failure=failure[0] if failure else None,raw_error=raw_error,electrical_verdict=None))
        paths += [summary]+[folder/n for n in r['files']]
    by={r['task']:r for r in results}
    def completed(names):
        return None if any(by[n]['status']=='pending' for n in names) else all(by[n]['raw_completed_12ns'] for n in names)
    tx_ok=completed(['tx_raw','tx_reduced']);coupled_ok=completed(['coupled_raw','coupled_reduced'])
    identity=dict(inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in ['observe_tx_isolation.py','run_ngspice.py','receiver_static_diagnosis.py']})
    dest=out/'raw_completion_observation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];dest.mkdir(parents=True,exist_ok=True)
    inference=('Both TX-only representations complete; coupled results are still pending.' if tx_ok and coupled_ok is None else
        'TX alone completes with both RC representations under these inputs; examine coupling/load/shared bias/initialization.' if tx_ok and coupled_ok is False else
        'Inspect the four bounded results before selecting another isolation experiment.')
    result=dict(identity=identity,results=results,terminal_cases=sum(r['status']=='terminal' for r in results),tx_only_both_completed=tx_ok,coupled_both_completed=coupled_ok,qualified_phy=False,
        inference=inference,
        scope='Raw numerical completion only; output levels, payload, timing, convergence beyond 12 ns and physical correctness are not admitted.')
    capture_manifest(dest/'summary.json',result);return dest/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(observe(a.artifact.resolve()),flush=True)
