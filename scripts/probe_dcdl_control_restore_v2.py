#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded fixes for measured SS40 complementary-control overshoot.

Retain the exact failed batch waveform and source topology. Compare only a
stronger control inverter and a minimum native MIM shunt, at the failing eight
code updates. Recharacterize all delays/stresses; no certificate is inherited.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import analyze_dcdl_batch_v2 as analysis
import probe_digital_dcdl_batch_v2 as original

h=original.h
ROOT=original.ROOT
VERSION='dcdl-complementary-control-restoration-v2.1'
VARIANTS=('inv4','mim2x2')


def fixture(out,spec):
    text=original.fixture(out,spec)
    if spec['restore']=='inv4':
        old=re.findall(r'(?m)^XEB\d+[^\n]+sky130_fd_sc_hd__inv_1$',text)
        if len(old)!=31:raise ValueError('Original inverter bank changed')
        for line in old:text=text.replace(line,line.replace('inv_1','inv_4'))
    elif spec['restore']=='mim2x2':
        caps='\n'.join(f'XCEB{i} EB{i} 0 sky130_fd_pr__cap_mim_m3_1 w=2 l=2' for i in range(31))
        text=text.replace('CLOAD OUT 0 20f',caps+'\nCLOAD OUT 0 20f')
    else:raise ValueError('Undeclared control restoration')
    return text


def prepare(failed_receipt):
    if not failed_receipt.is_relative_to(ROOT/'build/diagnostics/dcdl_batch_reanalysis_v2'):
        raise ValueError('Require an independently remeasured failed control case')
    r=json.loads((failed_receipt/'summary.json').read_text())
    if len(r['rows'])!=1 or r['rows'][0]['result']['custom_mos_stress_passed'] is not False:
        raise ValueError('Missing reproduced device-stress failure')
    row=r['rows'][0];parent=ROOT/r['identity']['artifact'];m=original.bound(parent)
    source=parent/row['task']['id']
    if (h.sha(parent/'manifest.json')!=r['identity']['manifest_sha256']
        or h.sha(source/'summary.json')!=row['producer_summary_sha256']
        or any(h.sha(source/n)!=v for n,v in row['files'].items())
        or analysis.measure(source,row['task'])!=row['result']):raise ValueError('Failure evidence changed')
    s=row['task']['spec']
    if (s['process'],s['temperature'],s['coarse'],s['codes'])!=('ss',40,0,list(range(8))):
        raise ValueError('Require the bounded SS40 first-code failure')
    specs=[dict(s,restore=v) for v in VARIANTS]
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcdl_batch_v2.py',ROOT/'scripts/analyze_dcdl_batch_v2.py',
        ROOT/'scripts/dcdl_cap_strong_v2.py',ROOT/'scripts/dcdl_cap_bank_v2.py',ROOT/'scripts/probe_digital_dcdl_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',
        ROOT/'build/apptainer/openlvds.sif.sha256']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=h.sha(parent/'manifest.json'),
        failed_receipt=str(failed_receipt.relative_to(ROOT)),failed_receipt_sha256=h.sha(failed_receipt/'summary.json'),
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],
        model_library=m['identity']['model_library'],model_library_sha256=m['identity']['model_library_sha256'],
        simulator=h.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcdl_control_restore_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    cells=(parent/'cells.spice').read_text();full=Path(identity['pdk']).read_text()
    found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__inv_4\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
    if len(found)!=1:raise ValueError('Missing native inverter')
    h.write(out/'cells.spice',cells+'\n'+found[0]+'\n')
    h.write(out/'coarse0.spice',(parent/'coarse0.spice').read_text());tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,devices=original.policy.circuit(0)[1],deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_control_restore_v2'):raise ValueError('Wrong control-restoration context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']
        or h.sha(ROOT/i['failed_receipt']/'summary.json')!=i['failed_receipt_sha256']
        or h.sha(Path(i['model_library']))!=i['model_library_sha256']):raise ValueError('Control-restoration inputs changed')
    for task in m['tasks']:
        if (out/task['id']/'bench.cir').read_text()!=fixture(out,task['spec']):raise ValueError('Control-restoration fixture changed')
    return m


def measure(folder,task):
    result=analysis.measure(folder,task)
    return dict(result,version=VERSION,restore=task['spec']['restore'],
        scope='Source control restoration, delay and custom MOS stress only; no all-PVT or physical admission')

@contextmanager
def profile():
    previous=original.bound,original.measure
    original.bound=bound;original.measure=measure
    try:yield
    finally:original.bound,original.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():original.run(a.artifact.resolve())
