#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand the verified clock-aware reset repair to all fifteen PVT conditions."""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_dcc_clock_hold_v2 as pilot
import verify_clock_repairs_v2 as evidence

base=pilot.base
ROOT=pilot.ROOT
VERSION='dcc-clock-aware-reset-full-pvt-v2.1'


def prepare(parent):
    report=evidence.report(parent);m=pilot.bound(parent)
    choices=[g for g in report['groups'] if g['reset_drive']==1 and g['cases']==12 and g['source_event_and_timing_passed']]
    if report['cases']!=24 or len(choices)!=1:raise ValueError('Clock-aware drive-one candidate did not pass its complete bounded pilot')
    files=[Path(__file__),ROOT/'scripts/probe_dcc_clock_hold_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/verify_clock_repairs_v2.py',ROOT/'scripts/verify_digital_clocking_v2.py',
        ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    req=json.loads((ROOT/'requirements.json').read_text())
    specs=[dict(process=p,temperature=t,mhz=f,slew_ps=s,phase_error_ps=e,buffers=0,drive=1,output_cell='inv_4',reset_drive=1)
        for p,t,f,s,e in itertools.product(req['process_corners'],req['temperatures_c'],req['clock_test_mhz'],[20,250],[0,-140,140])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=specs,reset_drive=1)
    out=ROOT/'build/diagnostics/dcc_clock_hold_pvt_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    base.write(out/'cells.spice',(parent/'cells.spice').read_text());base.write(out/'hold1.spice',pilot.circuit(1));tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',pilot.fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcc_clock_hold_pvt_v2'):raise ValueError('Wrong clock-aware PVT context')
    m=original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=h for n,h in i['parent_inputs'].items())):raise ValueError('Clock-aware PVT inputs changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure,base.lease;lease=base.lease
    def fair_lease(*args,**kwargs):kwargs['priority']=1;return lease(*args,**kwargs)
    base.bound=bound;base.measure=pilot.measure;base.lease=fair_lease
    try:yield
    finally:base.bound,base.measure,base.lease=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):
        with profile():base.run(out)
    elif a.action=='bound':print(json.dumps(bound(out),indent=2))
