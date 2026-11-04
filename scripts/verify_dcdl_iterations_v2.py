#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate and remeasure full-duration matched DCDL iteration experiments."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_dcdl_iterations_v2 as pilot

ROOT=pilot.ROOT
VERSION='independent-matched-native-dcdl-iteration-verification-v2.1'
REQUIRED={'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}


def compare(a,b):
    if [r['pulse'] for r in a['samples']]!=[r['pulse'] for r in b['samples']]:raise ValueError('Pulse epochs changed')
    if [r['device'] for r in a['terminal_stress']]!=[r['device'] for r in b['terminal_stress']]:raise ValueError('MOS comparison coverage changed')
    return dict(maximum_absolute_edge_delay_difference_ps=max(abs(x[k]-y[k]) for x,y in zip(a['samples'],b['samples']) for k in ['rise_delay_ps','fall_delay_ps']),
        maximum_absolute_mos_peak_difference_v=max(abs(x['max_terminal_difference_v']-y['max_terminal_difference_v']) for x,y in zip(a['terminal_stress'],b['terminal_stress'])),
        native_pulse_verdict_matches=a['native_pulse_passed']==b['native_pulse_passed'])


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m,pm=pilot.bound(out);i=m['identity'];parent=ROOT/i['parent'];pi=pm['identity'];p=pilot.parent_pilot
        cells,bank,orders,mos,_=p.libraries(ROOT/pi['compound'],ROOT/pi['fine'],Path(pi['source_library']))
        if (cells!=(parent/'cells.spice').read_text() or bank!=(parent/'bank.spice').read_text()
            or orders!=pi['orders'] or mos!=pi['devices']):raise ValueError('Parent native library/MOS regeneration changed')
        state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if (state['status']!='matched_iteration_pilot_complete' or state['errors']
            or state['cases']!=len(m['tasks']) or len(aggregate)!=len(m['tasks'])):raise ValueError('Require complete numerical-error-free iteration cases')
        files=[out/n for n in ['manifest.json','state.json','summary.json']];rows=[]
        for task,retained in zip(m['tasks'],aggregate):
            case=task['id'];folder=out/case;r=json.loads((folder/'summary.json').read_text())
            deck=p.fixture(parent,task['spec'],mos)
            if (r!=retained or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(deck)
                or not REQUIRED<=set(r['files']) or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Iteration case/raw/deck changed')
            measured=p.measure(folder,task['spec'],mos)
            if measured!=r['result']:raise ValueError('Iteration waveform remeasurement changed')
            comparison=None;baseline_folder=parent/case
            if (baseline_folder/'summary.json').exists():
                baseline=json.loads((baseline_folder/'summary.json').read_text())
                if (baseline['task']!=pm['tasks'][int(case)] or baseline['error'] is not None
                    or (baseline_folder/'bench.cir').read_text()!=deck or not REQUIRED<=set(baseline['files'])
                    or any(pilot.sha(baseline_folder/n)!=h for n,h in baseline['files'].items())):raise ValueError('Completed baseline witness changed or failed numerically')
                original=p.measure(baseline_folder,task['spec'],mos)
                if original!=baseline['result']:raise ValueError('Baseline remeasurement changed')
                comparison=compare(measured,original);files += [baseline_folder/n for n in ['summary.json',*baseline['files']]]
            rows.append(dict(task=task,result=measured,completed_baseline_comparison=comparison,
                             solver_wall_seconds=r['solver_wall_seconds'],qualified_phy=False))
            files += [folder/n for n in ['summary.json',*r['files']]]
        pilot.bound(out)
        code=[Path(__file__),Path(pilot.__file__),Path(p.__file__),ROOT/'scripts/probe_routed_dcdl_bank_v2.py',ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(path.relative_to(ROOT)):pilot.sha(path) for path in files+code})
        receipt=ROOT/'build/diagnostics/dcdl_iterations_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Iteration witness changed during verification')
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,rows=rows,
            all_declared_raw_waveforms_verified=True,qualified_phy=False,legal_code_table_admitted=False,
            scope='Regenerated full-duration matched ITL4 experiment, all MOS and two pulse epochs; comparisons only to completed baseline cases, no numerical speed/equivalence claim from partial files and no ROM/full-PVT/PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
