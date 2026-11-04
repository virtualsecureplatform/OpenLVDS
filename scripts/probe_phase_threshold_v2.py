#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native signed-threshold feasibility with the real conditioner and arbiter.

The new DLL sequencer needs actual positive/negative threshold paths. Insert
matched switched MIM branches AFTER analog conditioning, so their digital input
buffers do not reintroduce raw unequal-slew bias before conditioning. Test the
new load, full custom MOS stress and unchanged local-reference ripple limit.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import re
import numpy as np
import phase_threshold_pair_v2 as threshold
import probe_arbiter_reference_cap_v2 as parent_source
import verify_clock_repairs_v2 as evidence

base=parent_source.base
ROOT=parent_source.ROOT
analog=parent_source.original
VERSION='conditioned-native-phase-threshold-pilot-v2.1'


def fixture(out,spec,devices):
    text=analog.fixture(out,spec,devices)
    old='XD RFAST FFAST SW ARM QA QB VDD 0 tag_arbiter'
    if text.count(old)!=1:raise ValueError('Parent detector input closure changed')
    text=text.replace(old,f'.include "{out}/threshold.spice"\nVPOS POS 0 {1.8*spec["positive_offset"]}\n'
        'XT RFAST FFAST POS RTH FTH VDD 0 phase_threshold_pair\n'
        'XD RTH FTH SW ARM QA QB VDD 0 tag_arbiter')
    return text.replace('\n.end\n',' V(RTH) V(FTH) V(POS)\n.end\n')


def prepare(parent):
    proof=evidence.report(parent);m=parent_source.bound(parent)
    if (proof['cases']!=6 or proof['numerical_errors'] or len(proof['groups'])!=3
        or not all(g['source_sign_and_health_passed'] for g in proof['groups'])):
        raise ValueError('Require the independently passing MIM30 conditioner/arbiter pilot')
    files=[Path(__file__),Path(threshold.__file__),Path(parent_source.__file__),Path(analog.__file__),
        ROOT/'scripts/probe_tag_arbiter_v2.py',Path(evidence.__file__),ROOT/'scripts/verify_digital_clocking_v2.py',
        ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',ROOT/'scripts/dll_analog_frontend_v2_fingered.py',
        ROOT/'scripts/dll_analog_frontend_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(drive=1,swap=0,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf,positive_offset=d)
        for o,(sr,sf),d in itertools.product([-20,0,20],[(100,100),(20,200),(200,20)],[0,1])]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/phase_threshold_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    cells=(parent/'cells.spice').read_text();full=Path(identity['pdk']).read_text()
    for name in ['buf_8','buf_4','inv_1']:
        found=re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',full)
        if len(found)!=1:raise ValueError('Missing native threshold cell '+name)
        cells+='\n'+found[0]+'\n'
    base.write(out/'cells.spice',cells)
    for name in ['frontend.spice','bias.spice','arbiter.spice']:base.write(out/name,(parent/name).read_text())
    circuit,extra=threshold.circuit();base.write(out/'threshold.spice',circuit)
    devices=m['tasks'][0]['devices']+extra;tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/phase_threshold_v2'):raise ValueError('Wrong phase-threshold context')
    m=parent_source.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['parent_inputs'].items())):
        raise ValueError('Phase-threshold inputs changed')
    return m


def measure(folder,spec):
    result=analog.measure(folder,spec);names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    get=lambda n:w[:,names.index('v('+n.lower()+')')]
    if np.max(np.abs(get('POS')-1.8*spec['positive_offset']))>.01:raise ValueError('Unstable threshold control')
    offsets=[]
    for i in range(4):
        select=(t>=analog.SETTLE_PS+i*10000+1500)&(t<analog.SETTLE_PS+i*10000+6000)
        a=base.crossings(t[select],get('RTH')[select]);b=base.crossings(t[select],get('FTH')[select])
        if len(a)!=1 or len(b)!=1:raise ValueError('Missing/extra threshold-path event')
        offsets.append(float(b[0]-a[0]))
    expected=(1 if spec['offset_ps']>0 else -1) if spec['offset_ps'] else (1 if spec['positive_offset'] else -1)
    return dict(result,version=VERSION,correct_sign_fraction=sum(v==expected for v in result['votes'])/len(result['votes']),
        expected_vote=expected,positive_offset=spec['positive_offset'],threshold_feedback_minus_reference_ps=offsets,
        threshold_increment_ps=[a-b for a,b in zip(offsets,result['conditioned_feedback_minus_reference_ps'])],
        scope='SS40 static-control source threshold/conditioner/arbiter pilot only; no all-PVT, route updates, physical or DLL admission')


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
