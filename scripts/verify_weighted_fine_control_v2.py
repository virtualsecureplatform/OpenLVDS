#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate and remeasure every source/guarded fine-control bias case."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_weighted_fine_control_v2 as pilot

ROOT=pilot.ROOT
VERSION='independent-isolated-root-fine-control-driver-verification-v2.1'


def regenerate(out,m):
    i=m['identity'];modules,orders,devices,_=pilot.libraries(ROOT/i['clock'],Path(i['source_library']))
    if (set(modules)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in modules.items())
        or orders!=i['orders'] or devices!=i['devices']):raise ValueError('Fine-control native library/MOS regeneration changed')
    return devices


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete fine-control bias coverage')
    groups=[]
    for mode in pilot.circuit.MODES:
        selected=[r['result'] for r in rows if r['task']['spec']['variant']==mode]
        groups.append(dict(mode=mode,data_bias_cases=len(selected),component_pilot_passed=all(r['component_pilot_passed'] for r in selected),
            maximum_terminal_difference_v=max(r['maximum_terminal_difference_v'] for r in selected),
            control_settling_passed=all(r['control_settling_passed'] for r in selected),
            terminal_screen_passed=all(r['terminal_screen_passed'] for r in selected),qualified_phy=False))
    return groups


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);ds=regenerate(out,m);state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if state['status']!='fine_control_pilot_complete' or state['errors'] or state['cases']!=4 or len(aggregate)!=4:raise ValueError('Require four complete numerical-error-free control cases')
        paths=[out/n for n in ['manifest.json','summary.json','state.json',*m['libraries']]];rows=[]
        for task,retained in zip(m['tasks'],aggregate):
            folder=out/task['id'];r=json.loads((folder/'summary.json').read_text());spec=task['spec'];devices=ds[spec['variant']]
            if (r!=retained or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,devices)
                or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
                or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Fine-control task/raw/deck changed')
            measured=pilot.measure(folder,spec,devices)
            if measured!=r['result']:raise ValueError('Fine-control raw remeasurement changed')
            rows.append(dict(task=task,result=measured));paths += [folder/n for n in ['summary.json',*r['files']]]
        groups=assess(rows);pilot.bound(out)
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.circuit.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths+code})
        receipt=ROOT/'build/diagnostics/weighted_fine_control_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Fine-control witnesses changed during verification')
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,groups=groups,all_declared_raw_waveforms_verified=True,qualified_phy=False,
            scope='Independent four-case control/fine-load bias screen, source fine and native guarded-driver RC only; negative source reference retained, no full-bank range, physical fine, full-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
