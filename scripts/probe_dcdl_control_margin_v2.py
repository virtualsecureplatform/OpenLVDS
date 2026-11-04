#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check both directions and large thermometer jumps at 20/100/200 ps slew.

The 2x2 MIM shunt passes the first SS40 case with 18 mV stress headroom. Test
that geometry and 4x4 before using either in the complete characterization.
All supplies and the 1.95 V custom-device limit remain unchanged.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import re
import probe_dcdl_control_restore_v2 as restore

original=restore.original
h=restore.h
ROOT=restore.ROOT
VERSION='dcdl-control-shunt-bidirectional-margin-v2.1'
CODES=[0,31,0,16,0,8,31,0]


def fixture(out,spec):
    text=restore.fixture(out,dict(spec,restore='mim2x2'))
    if spec['restore']=='mim4x4':
        rows=re.findall(r'(?m)^XCEB\d+[^\n]+w=2 l=2$',text)
        if len(rows)!=31:raise ValueError('Reference shunt bank changed')
        for line in rows:text=text.replace(line,line.replace('w=2 l=2','w=4 l=4'))
    elif spec['restore']!='mim2x2':raise ValueError('Undeclared shunt geometry')
    for i in range(31):
        value=[1.8 if i<c else 0 for c in spec['codes']];points=[f'0 {value[0]}']
        half=spec['control_slew_ps']/2000
        for k in range(1,len(value)):points += [f'{k*10-half:g}n {value[k-1]}',f'{k*10+half:g}n {value[k]}']
        text,count=re.subn(r'(?m)^VE'+str(i)+r' E'+str(i)+r' 0 PWL\([^\n]+\)$',f'VE{i} E{i} 0 PWL('+' '.join(points)+')',text)
        if count!=1:raise ValueError('Original control source changed')
    return text


def prepare(parent):
    m=restore.bound(parent);state=json.loads((parent/'state.json').read_text())
    rows=json.loads((parent/'summary.json').read_text())['rows']
    if state['status']!='source_screen_complete' or [r['task'] for r in rows]!=m['tasks']:raise ValueError('Require terminal restoration pilot')
    good=[r for r in rows if r['task']['spec']['restore']=='mim2x2' and r['error'] is None and r['result']['custom_mos_stress_passed']]
    if len(good)!=1:raise ValueError('Missing passing shunt source')
    row=good[0];folder=parent/row['task']['id']
    if any(h.sha(folder/n)!=v for n,v in row['files'].items()) or restore.measure(folder,row['task'])!=row['result']:
        raise ValueError('Passing shunt witness changed')
    files=[Path(__file__),ROOT/'scripts/probe_dcdl_control_restore_v2.py',ROOT/'scripts/probe_digital_dcdl_batch_v2.py',
        ROOT/'scripts/analyze_dcdl_batch_v2.py',ROOT/'scripts/dcdl_cap_strong_v2.py',ROOT/'scripts/dcdl_cap_bank_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',
        ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(process='ss',temperature=40,coarse=0,codes=CODES,restore=v,control_slew_ps=s)
        for v,s in itertools.product(['mim2x2','mim4x4'],[20,100,200])]
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        inputs={str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=h.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcdl_control_margin_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ['cells.spice','coarse0.spice']:h.write(out/n,(parent/n).read_text())
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,devices=original.policy.circuit(0)[1],deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_control_margin_v2'):raise ValueError('Wrong control margin context')
    m=h.bound(out);i=m['identity']
    if i['version']!=VERSION or any(h.sha(ROOT/n)!=v for n,v in i['inputs'].items()) or h.sha(Path(i['model_library']))!=i['model_library_sha256']:
        raise ValueError('Control margin context changed')
    return m


def measure(folder,task):
    return dict(restore.analysis.measure(folder,task),version=VERSION,restore=task['spec']['restore'],control_slew_ps=task['spec']['control_slew_ps'])

@contextmanager
def profile():
    previous=original.bound,original.measure;original.bound=bound;original.measure=measure
    try:yield
    finally:original.bound,original.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():original.run(a.artifact.resolve())
