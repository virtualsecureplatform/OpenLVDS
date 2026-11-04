#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source feasibility of a MOS-switched MIM fine bank on the retained DCDL.

The baseline demonstrated insufficient fine range. This bounded experiment
checks two physical MIM geometries, zero/first/full fine codes and the first
two coarse settings. All custom MOS terminal pairs are observed and checked.
Sparse source results do not constitute a dense all-PVT legal-code table.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import numpy as np
import dcdl_cap_bank_v2 as policy
import probe_digital_dcdl_v2 as original

h=original.helpers
ROOT=original.ROOT
VERSION='source-dcdl-mim-fine-bank-pilot-v2.1'


def fixture(out,spec,lib):
    text=original.fixture(out,spec,lib)
    before='VIN IN 0 PWL(0 0 2n 0 2.2n 1.8 20n 1.8 20.2n 0)'
    if text.count(before)!=1:raise ValueError('Original fixture changed')
    text=text.replace(before,'BIN IN 0 V={0.9*(tanh((time-2.1n)/72.819138130147p)-tanh((time-20.1n)/72.819138130147p))}')
    # Every switch diffusion/body/gate voltage is either one of these probes or
    # a fixed rail. The 31 capacitor nodes must not be replaced by one proxy.
    return text.replace('V(VDD)\n.end','V(VDD) '+' '.join(f'V(XD:cap{i})' for i in range(31))+'\n.end')


def prepare(parent):
    m=original.bound(parent)
    pdk=Path(m['identity']['pdk']);model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    req=json.loads((ROOT/'requirements.json').read_text())
    if Path(os.environ['PDK_ROOT']).name!=req['pdk_version']:raise ValueError('Use the pinned SKY130 model')
    files=[Path(__file__),ROOT/'scripts/dcdl_cap_bank_v2.py',ROOT/'scripts/probe_digital_dcdl_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',
        ROOT/'scripts/spice_engine.py',ROOT/'clocking_v2.json',ROOT/'requirements.json',ROOT/'scripts/env.sh',
        ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(process='tt',temperature=25,coarse_count=16,fine_count=32,coarse=c,fine=f,variant=v)
        for v,c,f in itertools.product(policy.VARIANTS,[0,1],[0,1,31])]
    identity=dict(version=VERSION,policy=policy.VERSION,
        parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=h.sha(parent/'manifest.json'),
        code={str(p.relative_to(ROOT)):h.sha(p) for p in files},pdk=str(pdk),pdk_sha256=h.sha(pdk),
        model_library=str(model),model_library_sha256=h.sha(model),simulator=h.provenance(),specs=specs,
        input_slew_10_90_ps=160,scope='Source MIM/TG fine-range feasibility and custom-device stress only')
    out=ROOT/'build/diagnostics/digital_dcdl_cap_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    # Keep the same native logic library. The MIM/MOS models come from the
    # pinned process .lib rather than numerical equivalent capacitances.
    h.write(out/'cells.spice',(parent/'cells.spice').read_text());tasks=[]
    for n,spec in enumerate(specs):
        lib=f'dcdl_{n}.spice';text,devices=policy.circuit(spec['variant'],spec['coarse'],spec['fine'])
        h.write(out/lib,text);folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec,lib))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/digital_dcdl_cap_v2'):raise ValueError('Wrong MIM-bank context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or i['policy']!=policy.VERSION
        or h.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']
        or h.sha(Path(i['model_library']))!=i['model_library_sha256']):raise ValueError('MIM-bank context changed')
    for task in m['tasks']:
        text,devices=policy.circuit(task['spec']['variant'],task['spec']['coarse'],task['spec']['fine'])
        if text!=(out/f'dcdl_{task["id"]}.spice').read_text() or devices!=task['devices']:
            raise ValueError('MIM bank or observation contract changed')
    return m


original_measure=original.measure

def measure(folder):
    result=original_measure(folder)
    m=json.loads((folder.parent/'manifest.json').read_text())
    task=next(t for t in m['tasks'] if t['id']==folder.name)
    names,w=h.read_raw(folder/'bench.raw')
    get=lambda n: np.zeros(len(w)) if n=='VSS' else (w[:,names.index('v(vdd)')] if n=='VDD' else w[:,names.index('v(xd.'+n+')')])
    stress=[]
    for device in task['devices']:
        values=[get(n) for n in device['terminals']]
        worst=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=device['name'],max_terminal_difference_v=worst,limit_v=1.95,passed=worst<=1.95))
    return dict(result,custom_mos_stress=stress,custom_mos_stress_passed=all(d['passed'] for d in stress),
        scope='Sparse source MIM fine-range and all custom MOS stress only; no physical/closed-loop/PHY admission')

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
