#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand the independently verified MIM30 arbiter to fifteen PVT conditions.

These isolated calibration tags test both input-swap polarities. They do not
qualify continuous clocks, physical RC, 64-vote lock or a complete DLL.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_arbiter_reference_cap_v2 as pilot
import verify_clock_repairs_v2 as evidence

base=pilot.base
ROOT=pilot.ROOT
VERSION='analog-arbiter-mim30-pvt-v2.1'


def specifications(requirements):
    return [dict(process=p,temperature=t,drive=1,swap=w,offset_ps=o,
                 reference_slew_ps=sr,feedback_slew_ps=sf)
            for p,t,w,o,(sr,sf) in itertools.product(
                requirements['process_corners'],requirements['temperatures_c'],
                [0,1],[-20,20],[(100,100),(20,200),(200,20)])]


def fixture(out,spec,devices):
    text=pilot.original.fixture(out,spec,devices)
    if text.count('" ss\n')!=1 or text.count('.options device temp=40\n')!=1:
        raise ValueError('Parent fixture PVT declaration changed')
    return text.replace('" ss\n','" '+spec['process']+'\n').replace(
        '.options device temp=40\n',f'.options device temp={spec["temperature"]}\n')


def prepare(parent):
    report=evidence.report(parent);m=pilot.bound(parent)
    if (report['cases']!=6 or report['numerical_errors'] or len(report['groups'])!=3
        or not all(g['source_sign_and_health_passed'] for g in report['groups'])):
        raise ValueError('Require the complete independently verified MIM30 source pilot')
    files=[Path(__file__),Path(pilot.__file__),Path(pilot.original.__file__),
           ROOT/'scripts/probe_tag_arbiter_v2.py',Path(evidence.__file__),
           ROOT/'scripts/verify_digital_clocking_v2.py',
           ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',
           ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
           ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',
           ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',
           ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=specifications(json.loads((ROOT/'requirements.json').read_text()))
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):base.sha(parent/n)
                       for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],
        model_library=m['identity']['model_library'],model_library_sha256=m['identity']['model_library_sha256'],
        simulator=base.provenance(),specs=specs,reference_mim_um=[30,30])
    out=ROOT/'build/diagnostics/analog_arbiter_pvt_v2'/hashlib.sha256(
        json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ['frontend.spice','cells.spice','arbiter.spice','bias.spice']:
        base.write(out/name,(parent/name).read_text())
    devices=m['tasks'][0]['devices'];tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/analog_arbiter_pvt_v2'):
        raise ValueError('Wrong analog-arbiter PVT context')
    m=pilot.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=h for n,h in i['parent_inputs'].items())):
        raise ValueError('Analog-arbiter PVT inputs changed')
    return m


def measure(folder,spec):
    return dict(pilot.original.measure(folder,spec),
        scope='Isolated source tags across PVT and input swaps; no physical RC or DLL admission')


@contextmanager
def profile():
    previous=base.bound,base.measure;base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='bound':print(json.dumps(bound(out),indent=2))
    else:
        with profile():base.run(out)
