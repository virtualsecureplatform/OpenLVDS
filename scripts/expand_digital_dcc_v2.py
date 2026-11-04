#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand the remeasured output-inverter DCC survivor to all 15 PVT.

Source only; ideal opposite-phase stimuli isolate event handling. They cannot
qualify a DLL or replace the link's clock-generation/physical requirements.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_digital_dcc_output_v2 as screen

base=screen.base
ROOT=base.ROOT
VERSION='digital-dcc-output-survivor-pvt-v2.1'


def admit(parent):
    m=screen.bound(parent)
    state=json.loads((parent/'state.json').read_text())
    if state['status']!='source_screen_complete' or state['cases']!=8 or state['errors']!=0:
        raise ValueError('Require complete eight-case source screen')
    rows=json.loads((parent/'summary.json').read_text())['rows']; selected=[]
    if len(rows)!=len(m['tasks']) or [r['task'] for r in rows]!=m['tasks']:
        raise ValueError('Incomplete or altered source rows')
    for row in rows:
        folder=parent/row['task']['id']
        if (row['error'] is not None or any(base.sha(folder/n)!=h for n,h in row['files'].items())
            or base.measure(folder,row['task']['spec'])!=row['result']
            or json.loads((folder/'summary.json').read_text())!=row):
            raise ValueError('Source screen changed or failed measurement')
        spec=row['task']['spec']
        if spec['drive']==1 and spec['output_cell']=='inv_4':selected.append(row)
    if len(selected)!=1 or not selected[0]['result']['event_integrity_passed'] or not selected[0]['result']['symmetric_timing_passed']:
        raise ValueError('Chosen DCC topology did not pass source screen')
    return m


def prepare(parent):
    m=admit(parent)
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcc_output_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',ROOT/'clocking_v2.json']
    specs=[dict(process=p,temperature=t,mhz=f,slew_ps=s,phase_error_ps=e,buffers=0,drive=1,output_cell='inv_4')
        for p,t,f,s,e in itertools.product(['tt','ff','ss','fs','sf'],[0,25,40],[390,400,410],[20,250],[0,-140,140])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):base.sha(p) for p in parent.glob('*.json')},
        code={str(p.relative_to(ROOT)):base.sha(p) for p in files},pdk=m['identity']['pdk'],
        pdk_sha256=m['identity']['pdk_sha256'],simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/digital_dcc_pvt_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    base.write(out/'cells.spice',(parent/'cells.spice').read_text())
    base.write(out/'dcc.spice',screen.circuit(1,'inv_4'));tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir()
        deck=base.fixture(out,spec,'dcc.spice').replace('V(XD:feedback)','V(XD:QT) V(XD:feedback)')
        base.write(folder/'bench.cir',deck)
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcc_pvt_v2'):raise ValueError('Wrong PVT context')
    m=original_bound(out);i=m['identity']
    if i['version']!=VERSION or any(base.sha(ROOT/n)!=h for n,h in i['inputs'].items()):
        raise ValueError('DCC source input changed')
    return m

@contextmanager
def profile():
    old=base.bound;old_lease=base.lease
    def lease(*args,**kwargs):
        kwargs['priority']=1
        return old_lease(*args,**kwargs)
    base.bound=bound;base.lease=lease
    try:yield
    finally:base.bound=old;base.lease=old_lease

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
