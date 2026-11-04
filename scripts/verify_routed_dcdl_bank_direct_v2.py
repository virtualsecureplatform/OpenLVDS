#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate routed-bank decks/MOS coverage and independently reread raw data."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_routed_dcdl_bank_direct_v2 as pilot
import verify_routed_dcdl_bank_v2 as original

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='independent-direct-port-bank-static-pulse-and-slew-verification-v2.1'


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete direct-port bank coverage')
    groups=original.assess([r for r in rows if r['task']['spec']['input_slew_ps']==100])
    slow=[r['result'] for r in rows if r['task']['spec']['input_slew_ps']==250]
    if len(slow)!=1:raise ValueError('Missing maximum-input-slew minimum-code test')
    headroom=1e6/410/4-max(s[k+'_delay_ps'] for s in slow[0]['samples'] for k in ['rise','fall'])
    groups[0].update(input_slew_250ps_minimum_quarter_headroom_ps=headroom,
        sparse_feasibility_passed=bool(groups[0]['sparse_feasibility_passed'] and headroom>0 and slow[0]['native_pulse_passed']))
    return groups

def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];state=json.loads((out/'state.json').read_text())
        text=(out/'bank_rc.spice').read_text();_,_,mos=pilot.devices(text)
        if mos!=i['devices'] or i['specs']!=pilot.specifications():raise ValueError('Routed-bank MOS/PVT coverage changed')
        if (state['status']!='routed_bank_pilot_complete' or state['cases']!=len(i['specs']) or state['errors']
            or len(m['tasks'])!=len(i['specs'])):raise ValueError('Require all complete numerical-error-free routed-bank cases')
        aggregate=json.loads((out/'summary.json').read_text())['rows']
        if len(aggregate)!=len(m['tasks']):raise ValueError('Incomplete routed-bank aggregate')
        paths=[out/n for n in ['manifest.json','state.json','summary.json','bank_rc.spice']];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);retained=json.loads((folder/'summary.json').read_text())
            if (retained!=aggregate[n] or retained['task']!=task or retained['error'] is not None
                or task['spec']!=i['specs'][n] or task['id']!=str(n)
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,task['spec'],text)):raise ValueError('Routed-bank task/deck changed')
            required={'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}
            if not required<=set(retained['files']) or any(sha(folder/name)!=h for name,h in retained['files'].items()):raise ValueError('Routed-bank raw witness changed')
            measured=pilot.measure(folder,task['spec'],mos)
            if measured!=retained['result']:raise ValueError('Routed-bank raw remeasurement changed')
            rows.append(dict(task=task,result=measured));paths += [folder/name for name in ['summary.json',*sorted(retained['files'])]]
        groups=assess(rows);pilot.bound(out)
        witnesses={str(p.relative_to(ROOT)):sha(p) for p in paths}
        code=[Path(__file__),Path(pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',Path(original.__file__)]
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=witnesses,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        receipt=ROOT/'build/diagnostics/routed_dcdl_bank_direct_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        report=dict(identity=identity,groups=groups,sparse_feasibility_passed=all(g['sparse_feasibility_passed'] for g in groups),
            qualified_phy=False,legal_code_table_admitted=False,
            scope='Regenerated whole-bank RC decks/MOS coverage and all seven raw pulse cases; sparse two-PVT range/overlap plus SS40 maximum-input-slew minimum only, no dense ROM, updates, periodic clock or full-PVT admission')
        if any(sha(ROOT/n)!=h for n,h in witnesses.items()):raise ValueError('Routed-bank witnesses changed during verification')
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',report);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
