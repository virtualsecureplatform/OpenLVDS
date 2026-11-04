#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate and reread the sparse weighted-fine architecture experiment."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_weighted_fine_bank_v2 as pilot

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='independent-weighted-fine-source-native-core-pilot-verification-v2.1'


def regenerate(out,m):
    i=m['identity'];parent=ROOT/i['parent'];report=json.loads((parent/'summary.json').read_text());texts=[];orders={}
    for row in report['rows']:
        info=row['extraction'];texts.append(pilot.checked_netlist(info));orders[row['macro']]=info['ports']
    sc_paths=[Path(n) for n in i['pdk_files'] if n.endswith('/sky130_fd_sc_hd.spice')]
    if len(sc_paths)!=1:raise ValueError('Missing exact native control library')
    library=sc_paths[0].read_text()
    for short in ['conb_1','buf_4','buf_1','inv_1']:
        model=pilot.circuit.old.native.SC+short;text=pilot.core.physical.cell_definition(library,model);texts.append(text)
        orders[model]=pilot.circuit.parsing.definitions(text)[model][0]
    cells='\n'.join(texts)
    if orders!=i['orders'] or cells!=(out/'cells.spice').read_text():raise ValueError('Native-core/control regeneration changed')
    devices={}
    for v in pilot.circuit.SCALES:
        text=pilot.circuit.fine_cells(v)+pilot.circuit.source(v,orders)
        if text!=(out/(v+'.spice')).read_text():raise ValueError('Weighted fine geometry/topology changed')
        devices[v]=pilot.circuit.mapped_mos(cells+text)
    if devices!=i['devices']:raise ValueError('Weighted-bank MOS coverage changed')
    return devices


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete weighted-bank pilot')
    groups=[]
    for variant in pilot.circuit.SCALES:
        points={r['task']['spec']['coarse']:r['result'] for r in rows if r['task']['spec']['variant']==variant}
        first,following=points[0],points[1]
        overlap={k:min(s[k+'_delay_ps'] for s in first['samples'] if s['code']==31)
                   -max(s[k+'_delay_ps'] for s in following['samples'] if s['code']==0) for k in ['rise','fall']}
        groups.append(dict(variant=variant,process='ss',temperature=40,minimum_quarter_headroom_ps=first['minimum_quarter_headroom_ps'],
            coarse0_fine31_to_coarse1_fine0_overlap_ps=overlap,
            sparse_feasibility_passed=bool(first['minimum_quarter_headroom_ps']>0 and min(overlap.values())>=0
                                         and all(r['terminal_screen_passed'] for r in points.values()))))
    return groups


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];ds=regenerate(out,m);state=json.loads((out/'state.json').read_text())
        if (state['status']!='weighted_bank_pilot_complete' or state['cases']!=len(pilot.specifications()) or state['errors']
            or len(m['tasks'])!=len(pilot.specifications()) or i['specs']!=pilot.specifications()):raise ValueError('Require four complete numerical-error-free weighted-bank cases')
        aggregate=json.loads((out/'summary.json').read_text())['rows']
        if len(aggregate)!=len(m['tasks']):raise ValueError('Incomplete weighted-bank aggregate')
        paths=[out/n for n in ['manifest.json','state.json','summary.json',*m['libraries']]];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);r=json.loads((folder/'summary.json').read_text());spec=task['spec']
            if (r!=aggregate[n] or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,ds[spec['variant']])):raise ValueError('Weighted-bank task/deck changed')
            if (not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
                or any(sha(folder/name)!=h for name,h in r['files'].items())):raise ValueError('Weighted-bank raw witness changed')
            measured=pilot.measure(folder,spec,ds[spec['variant']])
            if measured!=r['result']:raise ValueError('Weighted-bank raw remeasurement changed')
            rows.append(dict(task=task,result=measured));paths += [folder/name for name in ['summary.json',*sorted(r['files'])]]
        groups=assess(rows);pilot.bound(out);files={str(p.relative_to(ROOT)):sha(p) for p in paths}
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.circuit.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=files,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        receipt=ROOT/'build/diagnostics/weighted_fine_bank_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        if any(sha(ROOT/n)!=h for n,h in files.items()):raise ValueError('Weighted-bank data changed during verification')
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,groups=groups,
            sparse_feasibility_passed=all(g['sparse_feasibility_passed'] for g in groups),qualified_phy=False,legal_code_table_admitted=False,
            scope='Regenerated source weighted-fine/native-core RC pilot and independent raw remeasurement; no fine/control/common-wire physical RC, dense ROM, full-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
