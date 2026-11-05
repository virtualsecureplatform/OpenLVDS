#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently regenerate and measure direct weighted-fine bank experiments."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_weighted_direct_v4 as pilot

ROOT=pilot.ROOT
VERSION='independent-direct-weighted-wide-power-repaired-fine-control-rc-verification-v2.3'


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete direct weighted matrix')
    groups=[]
    for mode in pilot.circuit.MODES:
        points={r['task']['spec']['coarse']:r['result'] for r in rows if r['task']['spec']['variant']==mode}
        first,following=points[0],points[1];steps=[];repeats=[]
        for coarse,result in sorted(points.items()):
            if [s['code'] for s in result['samples']]!=pilot.CODES:raise ValueError('Incomplete carry/repeat coverage')
            samples=result['samples'];lookup={s['code']:s for s in samples[:-1]}
            for edge in ['rise','fall']:
                for a,b in [(0,1),(15,16)]:
                    delta=lookup[b][edge+'_delay_ps']-lookup[a][edge+'_delay_ps']
                    steps.append(dict(coarse=coarse,edge=edge,codes=[a,b],step_ps=delta,passed=0<delta<=20))
                repeats.append(dict(coarse=coarse,edge=edge,absolute_repeat_difference_ps=abs(samples[-1][edge+'_delay_ps']-samples[0][edge+'_delay_ps'])))
        overlap={edge:min(s[edge+'_delay_ps'] for s in first['samples'] if s['code']==31)
                 -max(s[edge+'_delay_ps'] for s in following['samples'] if s['code']==0) for edge in ['rise','fall']}
        headroom=first['minimum_quarter_headroom_ps']
        monotonic=all(all(b[edge+'_delay_ps']>a[edge+'_delay_ps'] for a,b in zip(r['samples'][:-2],r['samples'][1:-1]))
                      for r in points.values() for edge in ['rise','fall'])
        groups.append(dict(mode=mode,process='ss',temperature=40,minimum_quarter_headroom_ps=headroom,
            coarse0_fine31_to_coarse1_fine0_overlap_ps=overlap,observed_single_code_steps=steps,
            sampled_fine_order_passed=monotonic,code_zero_repetition=repeats,
            sparse_feasibility_passed=bool(headroom>0 and min(overlap.values())>=0 and monotonic
                and all(s['passed'] for s in steps) and all(r['terminal_screen_passed'] for r in points.values()))))
    return groups


def regenerate(out,m):
    i=m['identity'];modules,orders,devices,_=pilot.libraries(ROOT/i['compound'],ROOT/i['guard'],ROOT/i['fine_cells'],ROOT/i['repair'],ROOT/i['clock'],Path(i['source_library']))
    if (set(modules)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in modules.items())
        or orders!=i['orders'] or devices!=i['devices']):raise ValueError('Direct weighted library/MOS regeneration changed')
    return devices


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);gate=json.loads((out/'control_gate.json').read_text())
        proof=pilot.control_gate.require(ROOT/gate['receipt'],ROOT/m['identity']['clock'],ROOT/m['identity']['fine_cells'],ROOT/m['identity']['repair'])
        if gate!=proof:raise ValueError('Full-bank fine-control prerequisite changed')
        ds=regenerate(out,m);state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if (state['status']!='weighted_direct_pilot_complete' or state['errors'] or state['cases']!=len(m['tasks'])
            or len(aggregate)!=len(m['tasks'])):raise ValueError('Require complete numerical-error-free direct weighted pilot')
        paths=[out/n for n in ['manifest.json','state.json','summary.json','control_gate.json',*m['libraries']]];rows=[]
        for task,retained in zip(m['tasks'],aggregate):
            folder=out/task['id'];r=json.loads((folder/'summary.json').read_text());spec=task['spec'];devices=ds[spec['variant']]
            if (r!=retained or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,devices)
                or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
                or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Direct weighted task/raw/deck changed')
            measured=pilot.measure(folder,spec,devices)
            if measured!=r['result']:raise ValueError('Direct weighted remeasurement changed')
            rows.append(dict(task=task,result=measured));paths += [folder/n for n in ['summary.json',*r['files']]]
        groups=assess(rows);pilot.bound(out)
        paths += [ROOT/gate['receipt']/'summary.json']
        if pilot.control_gate.require(ROOT/gate['receipt'],ROOT/m['identity']['clock'],ROOT/m['identity']['fine_cells'],ROOT/m['identity']['repair'])!=proof:raise ValueError('Fine-control prerequisite changed during bank verification')
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.circuit.__file__),Path(pilot.previous.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths+code})
        receipt=ROOT/'build/diagnostics/weighted_direct_verification_v4'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Direct weighted evidence changed during verification')
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,groups=groups,
            all_declared_waveforms_verified=True,sparse_feasibility_passed=all(g['sparse_feasibility_passed'] for g in groups),
            qualified_phy=False,legal_code_table_admitted=False,
            scope='Two regenerated direct-port full-bank cases with routed guard-pair, fine-cell and guarded fine-driver RC; source coarse controls/shared MIM, ideal common wires; observed LSB/carry only, no whole-bank RC, dense-code, periodic-clock, full-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
