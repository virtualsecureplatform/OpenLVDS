#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate and independently remeasure the matched native NAND2-pair pilot."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_forward_pair_v2 as pilot
from run_native_binary_v2 import translate

ROOT=pilot.ROOT
VERSION='independent-native-forward-pair-idle-pulse-stress-verification-v2.1'


def regenerate(out,m):
    i=m['identity'];modules,orders,devices,_=pilot.libraries(ROOT/i['original'],ROOT/i['shunted'])
    if (set(modules)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in modules.items())
        or orders!=i['orders'] or devices!=i['devices']):raise ValueError('Native pair library/MOS regeneration changed')
    return orders,devices


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Require both input orientations for both native pairs')
    groups=[]
    for variant in pilot.MODELS:
        selected=[r for r in rows if r['task']['spec']['variant']==variant]
        complete=all(r['error'] is None and r['result'] is not None for r in selected)
        groups.append(dict(variant=variant,cases=len(selected),numerically_complete=complete,
                           isolated_pilot_passed=complete and all(r['result']['isolated_pilot_passed'] for r in selected),
                           numerical_failures=sum(r['error'] is not None for r in selected),qualified_phy=False))
    comparisons=[]
    for pin in ['B','A']:
        selected={r['task']['spec']['variant']:r for r in rows if r['task']['spec']['toggle_pin']==pin}
        available=all(r['error'] is None and r['result'] is not None and r['result']['isolated_pilot_passed'] for r in selected.values())
        delta=None
        if available:
            delay={variant:{edge:sum(e['delay_ps'] for e in row['result']['events'] if e['output_edge']==edge)/2
                            for edge in ['rise','fall']} for variant,row in selected.items()}
            delta={edge:delay['shunted'][edge]-delay['original'][edge] for edge in ['rise','fall']}
        comparisons.append(dict(toggle_pin=pin,timing_comparison_available=available,shunted_minus_original_delay_ps=delta,
                                 scope='Observed matched isolated propagation difference only; no bank or runtime-speedup admission'))
    return groups,comparisons


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);orders,devices=regenerate(out,m)
        state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if state['status']!='forward_pair_complete' or state['cases']!=4 or len(aggregate)!=4:
            raise ValueError('Require all four terminal pair tasks')
        paths=[out/n for n in ['manifest.json','summary.json','state.json',*m['libraries']]];rows=[]
        for task,retained in zip(m['tasks'],aggregate):
            folder=out/task['id'];row=json.loads((folder/'summary.json').read_text());spec=task['spec'];ds=devices[spec['variant']]
            if (row!=retained or row['task']!=task
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,orders[spec['variant']],ds)
                or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
                or any(pilot.sha(folder/n)!=h for n,h in row['files'].items())
                or (folder/'bench.ngspice.cir').read_text()!=translate((folder/'bench.cir').read_text())[0]):
                raise ValueError('Matched pair task/deck/raw witness changed')
            if row['error'] is None:
                result=pilot.measure(folder,spec,ds)
                if result!=row['result']:raise ValueError('Native pair raw remeasurement changed')
                rows.append(dict(task=task,result=result,error=None))
            else:
                if row['result'] is not None:raise ValueError('Numerically failed pair cannot supply an electrical result')
                failure=pilot.diagnosis.failure((folder/'ngspice.log').read_text())
                rows.append(dict(task=task,result=None,error=row['error'],numerical_failure=failure))
            paths += [folder/n for n in ['summary.json',*row['files']]]
        if state['errors']!=sum(r['error'] is not None for r in rows):raise ValueError('Numerical failure count changed')
        groups,comparisons=assess(rows);pilot.bound(out)
        code=[Path(__file__),Path(pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/run_native_binary_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths+code})
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Matched pair evidence changed during verification')
        receipt=ROOT/'build/diagnostics/forward_pair_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False)
        pilot.atomic(receipt/'summary.json',dict(identity=identity,rows=rows,groups=groups,comparisons=comparisons,
            all_cases_accounted_for=True,all_successful_raw_waveforms_verified=True,
            all_declared_raw_waveforms_verified=all(r['error'] is None for r in rows),
            shunted_isolated_pilot_passed=next(g['isolated_pilot_passed'] for g in groups if g['variant']=='shunted'),qualified_phy=False,
            scope='Independent matched native pair component screen; completed numerical failures retained as failures; no whole-bank convergence, code ROM, PVT, speedup or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
