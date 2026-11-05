#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate native drive/shunt isolation and independently remeasure 8ns traces."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import probe_routed_return_drive_v2 as pilot
import run_native_binary_v2 as runner

ROOT=pilot.ROOT
VERSION='independent-routed-return-native-drive-shunt-isolation-v2.1'
CONTEXT='routed_return_drive_verification_v2'
REQUIRED={'bank.spice','bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];receipt=ROOT/i['prefix_receipt'];pilot.diagnosis.verify(receipt)
        dr=json.loads((receipt/'summary.json').read_text());di=dr['identity'];parent=ROOT/i['parent']
        pm,bank,pair,paths=pilot.components(parent,ROOT/i['pair_receipt'])
        if (bank!=(out/'baseline.spice').read_text() or pair!=(out/'pair.spice').read_text()
            or di['parent']!=i['parent'] or di['task']['spec']!=i['baseline_spec']):
            raise ValueError('Native whole-bank/guard-pair or matched prefix cannot be regenerated')
        state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if state!={'status':'return_drive_diagnostic_complete','cases':2,'errors':0,'qualified_phy':False} or len(aggregate)!=2:
            raise ValueError('Require both complete numerical-error-free 8ns diagnostics')
        names,w,binding,offset=pilot.diagnosis.prefix(parent/di['case']/'bench.raw',di['raw']['complete_records'])
        if binding!=di['raw']:raise ValueError('Matched original prefix changed')
        k=int(np.searchsorted(w[:,names.index('time')],pilot.STOP,side='right'))
        if k<2 or w[k-1,names.index('time')]<pilot.STOP-2.1e-12:raise ValueError('Baseline lacks the complete first-pulse window')
        baseline=pilot.analyze(names,w[:k],pm['identity']['witness']);rows=[];comparisons=[]
        paths += [receipt/'summary.json',out/'manifest.json',out/'state.json',out/'summary.json',out/'baseline.spice',out/'pair.spice']
        for number,(task,retained) in enumerate(zip(m['tasks'],aggregate)):
            folder=out/task['id'];r=json.loads((folder/'summary.json').read_text());text,devices,added=pilot.augment(bank,pair,task['spec'],pm['identity']['witness']['devices'])
            translated,_=runner.translate((folder/'bench.cir').read_text())
            if (r!=retained or task['id']!=str(number) or r['task']!=task or r['error'] is not None
                or not REQUIRED<=set(r['files']) or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())
                or (folder/'bank.spice').read_text()!=text or (folder/'bench.ngspice.cir').read_text()!=translated
                or devices!=i['witness']['devices'] or added!=i['added_native_mos']):
                raise ValueError('Native return-drive library/witness/deck/raw evidence changed')
            result=pilot.measure(folder,task['spec'],i['witness'])
            if result!=r['result']:raise ValueError('Native return-drive waveform remeasurement changed')
            rows.append(dict(task=task,result=result));comparisons.append(dict(case=task['id'],tag=task['spec']['tag'],
                baseline_peak_v=baseline['terminal_observations']['maximum_observed_terminal_difference_v'],
                candidate_peak_v=result['terminal_observations']['maximum_observed_terminal_difference_v'],
                baseline_violating_devices=baseline['terminal_observations']['violating_devices'],candidate_violating_devices=result['terminal_observations']['violating_devices'],
                baseline_headroom_ps=baseline['minimum_quarter_headroom_ps'],candidate_headroom_ps=result['minimum_quarter_headroom_ps'],
                first_pulse_diagnostic_passed=result['first_pulse_diagnostic_passed']))
            paths += [folder/n for n in ['summary.json',*r['files']]]
        if pilot.diagnosis.payload_sha(parent/di['case']/'bench.raw',offset,binding['payload_bytes'])!=binding['payload_sha256']:
            raise ValueError('Original consumed prefix changed during verification')
        pilot.bound(out);paths += [Path(__file__),Path(pilot.__file__),Path(pilot.diagnosis.__file__),Path(runner.__file__)]
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),baseline_prefix=binding,
            inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths})
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Return-drive evidence changed during verification')
        receipt=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,rows=rows,
            matched_first_pulse_baseline=baseline,comparisons=comparisons,all_declared_raw_waveforms_verified=True,
            all_first_pulse_diagnostics_passed=all(r['result']['first_pulse_diagnostic_passed'] for r in rows),
            electrical_qualification_passed=False,legal_code_table_admitted=False,qualified_phy=False,
            scope='Two complete 8ns native drive/shunt diagnostic traces versus the exact bounded original first pulse; no new physical shared-wire/MIM geometry, full code/PVT timing or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
