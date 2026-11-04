#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test the retained differential clock conditioner before the tagged arbiter.

Both placements of standard-cell conditioning reverse some +/-20 ps races
under unequal slew. Reuse the exact tail140_w20 source topology that previously
passed its independent analog screen, but qualify this NEW load/arbiter pair.
The analog blocks supply only edge conditioning; delay codes remain digital.
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
import dll_analog_frontend_v2_tailtrim as frontend
import probe_tag_arbiter_v2 as core

base=core.base
ROOT=core.ROOT
VERSION='analog-conditioned-tagged-arbiter-pilot-v2.1'
SETTLE_PS=200000


def fixture(out,spec,devices):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    sr=spec['reference_slew_ps']/1000;sf=spec['feedback_slew_ps']/1000
    delay=202+sr/2-sf/2+spec['offset_ps']/1000
    text=(f'OpenLVDS {VERSION}\n.lib "{model}" ss\n.include "{out}/cells.spice"\n'
        f'.include "{out}/arbiter.spice"\n.include "{out}/frontend.spice"\n.include "{out}/bias.spice"\n'
        '.options device temp=40\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VDD VDD 0 1.8\nVDDIO VDDIO 0 3.3\nIREF PB 0 DC 35u\nXB PB NB VDDIO 0 lvds_bias\n'
        f'VSW SW 0 {1.8*spec["swap"]}\n'
        'VARM ARM 0 PULSE(0 1.8 201n 20p 20p 5.98n 10n)\n'
        f'VR R 0 PULSE(0 1.8 202n {sr}n {sr}n {1.25-sr}n 10n)\n'
        f'VF F 0 PULSE(0 1.8 {delay}n {sf}n {sf}n {1.25-sf}n 10n)\n'
        f'XF R F RFAST FFAST PB VDDIO VDD 0 {frontend.PAIR}\n'
        'XD RFAST FFAST SW ARM QA QB VDD 0 tag_arbiter\nCQA QA 0 5f\nCQB QB 0 5f\n'
        '.tran 1p 242n 0 1p\n')
    mapping={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD','VDDIO':'VDDIO','PB':'PB'}
    terminals={mapping.get(n,n) for d in devices for n in d['terminals'] if n!='0'}
    probes=sorted(terminals|{'R','F','ARM','QA','QB','RFAST','FFAST','XD:a','XD:b','XD:ha','XD:hb','XD:oa','XD:ob','VDD','VDDIO','PB','NB','XF:VCM'})
    return text+'.print tran '+' '.join('V('+n+')' for n in probes)+'\n.end\n'


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/dll_analog_frontend_timing_tailtrim'):
        raise ValueError('Require the retained analog timing screen')
    pm=json.loads((parent/'manifest.json').read_text());report=json.loads((parent/'summary.json').read_text())
    if report['analog_source_screen_passed'] is not True or 'tail140_w20' not in report['ranked_survivors']:
        raise ValueError('Missing retained source survivor')
    library=parent/'tail140_w20.spice';source=library.read_text();analog,devices=frontend.circuit('tail140_w20')
    if analog not in source:raise ValueError('Retained frontend topology differs')
    bias=re.findall(r'(?ims)^\.subckt\s+lvds_bias\s[^\n]*\n.*?^\.ends\b[^\n]*',source)
    if len(bias)!=1 or bias[0].splitlines()[0].split()[2:]!=['IREF','NB','VDDIO','VSS']:
        raise ValueError('Retained native bias closure changed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    files=[Path(__file__),ROOT/'scripts/probe_tag_arbiter_v2.py',ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',
        ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(drive=1,swap=0,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf)
        for o,(sr,sf) in itertools.product([-20,20],[(100,100),(20,200),(200,20)])]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):base.sha(p) for p in [library,parent/'manifest.json',parent/'summary.json']},
        pdk=str(pdk),pdk_sha256=base.sha(pdk),model_library=str(model),model_library_sha256=base.sha(model),
        simulator=base.provenance(),specs=specs,frontend=frontend.VERSION,variant='tail140_w20',settle_ps=SETTLE_PS)
    out=ROOT/'build/diagnostics/analog_conditioned_arbiter_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);full=pdk.read_text();cells=''
    for name in ['mux2_1','buf_1','or2_1','and2_1','nand2_4']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native cell '+name)
        cells+=found[0]+'\n'
    base.write(out/'cells.spice',cells);base.write(out/'arbiter.spice',core.circuit(1))
    base.write(out/'frontend.spice',analog);base.write(out/'bias.spice',bias[0]+'\n');tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def measure(folder,spec):
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1]<241999.99:raise ValueError('Incomplete analog-conditioned arbiter waveform')
    def get(n):
        mapping={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD'}
        return np.zeros(len(t)) if n=='0' else w[:,names.index('v('+mapping.get(n,n).replace(':','.').lower()+')')]
    votes=[];analog=[];conditioned=[]
    for i in range(4):
        start=SETTLE_PS+i*10000;when=start+6000
        held=[float(np.interp(when,t,get('XD:'+n))) for n in ['ha','hb']]
        if min(held)<1.62:raise ValueError('Missing retained conditioned tag')
        for n in ['ha','hb']:
            if np.interp(start+9000,t,get('XD:'+n))>.18:raise ValueError('Conditioned tags did not clear')
        a=float(np.interp(when,t,get('QA')));b=float(np.interp(when,t,get('QB')))
        if spec['swap']:a,b=b,a
        analog.append([a,b]);state=lambda v:0 if v<=.18 else (1 if v>=1.62 else None)
        pair=state(a),state(b);votes.append(1 if pair==(0,1) else (-1 if pair==(1,0) else (None if None in pair else 0)))
        mask=(t>=start+1500)&(t<start+5000)
        a=base.crossings(t[mask],get('RFAST')[mask]);b=base.crossings(t[mask],get('FFAST')[mask])
        if len(a)!=1 or len(b)!=1:raise ValueError('Missing/extra analog-conditioned edge')
        conditioned.append(float(b[0]-a[0]))
    task=next(q for q in json.loads((folder.parent/'manifest.json').read_text())['tasks'] if q['id']==folder.name)
    stress=[]
    for device in task['devices']:
        voltages=[get(n) for n in device['terminals']]
        maximum=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(voltages,2))
        limit=5.5 if device['model']==frontend.P5 else 1.95
        stress.append(dict(device=device['name'],max_terminal_difference_v=maximum,limit_v=limit,passed=maximum<=limit))
    ref=get('XF:VCM')[t>=SETTLE_PS];ref_ok=bool(np.max(np.abs(ref-.9))<=.01)
    expected=1 if spec['offset_ps']>0 else -1
    return dict(votes=votes,settled_output_voltages_v=analog,conditioned_feedback_minus_reference_ps=conditioned,
        correct_sign_fraction=sum(v==expected for v in votes)/len(votes),frontend_stress=stress,
        frontend_stress_passed=all(d['passed'] for d in stress),common_mode_min_v=float(ref.min()),common_mode_max_v=float(ref.max()),
        common_mode_passed=ref_ok,qualified_phy=False,detector_admitted=False,
        scope='Six-case new frontend/arbiter-load pilot only; no reset/disable, all-PVT, physical or DLL admission')

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/analog_conditioned_arbiter_v2'):raise ValueError('Wrong analog-conditioned context')
    m=original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['inputs'].items())):raise ValueError('Analog-conditioned inputs changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure;base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
