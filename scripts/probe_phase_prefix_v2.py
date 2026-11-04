#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native equivalence candidate: shorten only the 200 ns quiescent prefix.

Use the complete passing six-case MIM4-base source repair as the long witness.
Rebase only input/arm PULSE delays and stop time; all transistor/MIM geometry,
supplies, stimulus widths/periods and 1 ps maximum step remain unchanged.
Independent paired waveform equivalence is required before reuse elsewhere.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import measure_phase_threshold_v3 as analysis
import probe_phase_threshold_load_v2 as parent_source
import verify_phase_threshold_load_v2 as evidence

base=parent_source.base
ROOT=parent_source.ROOT
VERSION='native-threshold-quiet-prefix-equivalence-v2.1'
PREFIX_PS=20000


def fixture(out,spec,devices):
    text=parent_source.parent_source.fixture(out,spec,devices)
    delta=spec['settle_ps']/1000-200
    # Voltage PULSE arguments are V1 V2 TD TR TF PW PER. All three sources
    # retain their edge shape, width and repetition interval.
    def change(match):
        words=match[2].split()
        if len(words)!=7 or not words[2].endswith('n'):raise ValueError('Parent pulse declaration changed')
        words[2]=f'{float(words[2][:-1])+delta:.12g}n'
        return match[1]+' '.join(words)+')'
    text,count=re.subn(r'(?m)^(V(?:ARM|R|F)\s+\S+\s+0\s+PULSE\()([^\n)]+)\)',change,text)
    if count!=3 or text.count('.tran 1p 242n 0 1p')!=1:raise ValueError('Parent time-origin fixture changed')
    return text.replace('.tran 1p 242n 0 1p',f'.tran 1p {spec["settle_ps"]/1000+42:g}n 0 1p')


def prepare(parent):
    proof=evidence.report(parent);m=parent_source.bound(parent)
    if proof['cases']!=6 or proof['source_threshold_and_health_passed'] is not True:
        raise ValueError('Require complete passing matched-slew load repair')
    rows=json.loads((parent/'summary.json').read_text())['rows']
    for row in rows:
        task=row['task'];long_task=dict(task,spec=dict(task['spec'],settle_ps=200000))
        measured=analysis.measure(parent/task['id'],long_task)
        for key,value in row['result'].items():
            if key in measured and key not in ['scope','version'] and measured[key]!=value:
                raise ValueError('Explicit-origin analyzer differs from retained long measurement: '+key)
    files=[Path(__file__),Path(analysis.__file__),Path(parent_source.__file__),Path(evidence.__file__),
        ROOT/'scripts/probe_phase_threshold_v2.py',ROOT/'scripts/phase_threshold_pair_v2.py',
        ROOT/'scripts/probe_arbiter_reference_cap_v2.py',ROOT/'scripts/probe_analog_conditioned_arbiter_v2.py',
        ROOT/'scripts/probe_tag_arbiter_v2.py',ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',
        ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/verify_digital_clocking_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(t['spec'],settle_ps=PREFIX_PS) for t in m['tasks']]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/phase_prefix_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ['cells.spice','frontend.spice','bias.spice','arbiter.spice','threshold.spice']:
        base.write(out/name,(parent/name).read_text())
    tasks=[]
    for t,spec in zip(m['tasks'],specs):
        folder=out/t['id'];folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,t['devices']))
        tasks.append(dict(id=t['id'],spec=spec,devices=t['devices'],deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/phase_prefix_v2'):raise ValueError('Wrong prefix-equivalence context')
    m=parent_source.parent_source.parent_source.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['parent_inputs'].items())):raise ValueError('Prefix-equivalence inputs changed')
    return m


def measure(folder,spec):
    tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks']
    task=next(t for t in tasks if t['id']==folder.name)
    return dict(analysis.measure(folder,task),version=VERSION)


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
