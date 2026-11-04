#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain the correct-sign analog arbiter and reduce reference feedthrough.

The six-case new-load pilot exceeded the unchanged 10 mV reference limit by
255 uV. Change only its native MIM reference capacitor from 22x22 to 30x30 um.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_analog_conditioned_arbiter_v2 as original

base=original.base
ROOT=original.ROOT
VERSION='analog-arbiter-reference-mim30-v2.1'


def prepare(parent):
    m=original.bound(parent);state=json.loads((parent/'state.json').read_text())
    rows=json.loads((parent/'summary.json').read_text())['rows']
    if (state['status']!='source_screen_complete' or len(rows)!=6 or [r['task'] for r in rows]!=m['tasks']
        or any(r['error'] is not None or r['result']['correct_sign_fraction']!=1 or not r['result']['frontend_stress_passed'] for r in rows)
        or all(r['result']['common_mode_passed'] for r in rows)):
        raise ValueError('Require the complete correct-sign/reference-failed six-case source pilot')
    for row in rows:
        folder=parent/row['task']['id']
        if any(base.sha(folder/n)!=h for n,h in row['files'].items()) or original.measure(folder,row['task']['spec'])!=row['result']:
            raise ValueError('Reference failure witness changed')
    files=[Path(__file__),ROOT/'scripts/probe_analog_conditioned_arbiter_v2.py',ROOT/'scripts/probe_tag_arbiter_v2.py',
        ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    i=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=m['identity']['specs'],reference_mim_um=[30,30])
    out=ROOT/'build/diagnostics/arbiter_reference_cap_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    before='XCM VCM VSS sky130_fd_pr__cap_mim_m3_1 w=22 l=22'
    text=(parent/'frontend.spice').read_text()
    if text.count(before)!=1:raise ValueError('Original reference capacitor changed')
    base.write(out/'frontend.spice',text.replace(before,before.replace('w=22 l=22','w=30 l=30')))
    for name in ['cells.spice','arbiter.spice','bias.spice']:base.write(out/name,(parent/name).read_text())
    tasks=[]
    for task in m['tasks']:
        folder=out/task['id'];folder.mkdir();base.write(folder/'bench.cir',original.fixture(out,task['spec'],task['devices']))
        tasks.append(dict(task,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out

original_bound=base.bound

def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/arbiter_reference_cap_v2'):raise ValueError('Wrong reference-cap context')
    m=original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=h for n,h in i['parent_inputs'].items())):raise ValueError('Reference-cap inputs changed')
    return m

@contextmanager
def profile():
    previous=base.bound,base.measure;base.bound=bound;base.measure=original.measure
    try:yield
    finally:base.bound,base.measure=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
