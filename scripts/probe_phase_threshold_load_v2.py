#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Damp the measured off-branch undershoot without changing threshold units.

Two terminal immutable source cases reproduce -0.156 V at the lightly loaded
buf_8 node, violating PMOS node/body stress. Increase only the matched base MIM
capacitors from 2x2 to 4x4; retain 2x2 switched units and control shunts. The
parent's other cases may continue; never lock, alter or restart that producer.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_phase_threshold_v2 as parent_source
import verify_digital_clocking_v2 as binary

base=parent_source.base
ROOT=parent_source.ROOT
VERSION='conditioned-phase-threshold-mim4-base-pilot-v2.1'


def circuit(text):
    for suffix in ['r','f']:
        old=f'XCBASE{suffix} node_{suffix} VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=2'
        if text.count(old)!=1:raise ValueError('Original matched base load changed')
        text=text.replace(old,old.replace('w=2 l=2','w=4 l=4'))
    return text


def prepare(parent):
    m=parent_source.bound(parent);witnesses={};failed=[]
    for case in ['0','1']:
        folder=parent/case;path=folder/'summary.json';stamp=base.sha(path);row=json.loads(path.read_text())
        task=m['tasks'][int(case)]
        if (row['task']!=task or row['error'] is not None or row['result']['correct_sign_fraction']!=1
            or row['result']['frontend_stress_passed'] is not False or task['spec']['offset_ps']!=-20
            or (task['spec']['reference_slew_ps'],task['spec']['feedback_slew_ps'])!=(100,100)
            or task['spec']['positive_offset']!=int(case)):
            raise ValueError('Require both complete correct-sign/stress-failed matched cases')
        if not binary.REQUIRED<=set(row['files']) or any(base.sha(folder/n)!=v for n,v in row['files'].items()):
            raise ValueError('Failure output changed or incomplete')
        binary.export_matches_raw(folder)
        if parent_source.measure(folder,task['spec'])!=row['result']:raise ValueError('Stress failure did not reproduce')
        if stamp!=base.sha(path) or any(base.sha(folder/n)!=v for n,v in row['files'].items()):
            raise ValueError('Failure case changed during independent reading')
        witnesses[str(path.relative_to(ROOT))]=stamp
        witnesses.update({str((folder/n).relative_to(ROOT)):v for n,v in row['files'].items()});failed.append(row)
    files=[Path(__file__),Path(parent_source.__file__),ROOT/'scripts/phase_threshold_pair_v2.py',Path(binary.__file__),
        ROOT/'scripts/probe_arbiter_reference_cap_v2.py',ROOT/'scripts/probe_analog_conditioned_arbiter_v2.py',
        ROOT/'scripts/probe_tag_arbiter_v2.py',ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',
        ROOT/'scripts/dll_analog_frontend_v2_fingered.py',ROOT/'scripts/dll_analog_frontend_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',
        ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',
        ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(failed[0]['task']['spec'],offset_ps=o,positive_offset=d) for o,d in itertools.product([-20,0,20],[0,1])]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        parent_manifest_sha256=base.sha(parent/'manifest.json'),failure_witnesses=witnesses,
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/phase_threshold_load_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ['cells.spice','frontend.spice','bias.spice','arbiter.spice']:base.write(out/name,(parent/name).read_text())
    base.write(out/'threshold.spice',circuit((parent/'threshold.spice').read_text()));tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();devices=m['tasks'][0]['devices']
        base.write(folder/'bench.cir',parent_source.fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/phase_threshold_load_v2'):raise ValueError('Wrong threshold-load context')
    m=parent_source.parent_source.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or base.sha(ROOT/i['parent']/'manifest.json')!=i['parent_manifest_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['failure_witnesses'].items())):
        raise ValueError('Threshold load-repair inputs changed')
    return m


def measure(folder,spec):
    return dict(parent_source.measure(folder,spec),version=VERSION,
        scope='Matched-slew SS40 base-load repair only; no unequal-slew, all-PVT, physical or DLL admission')


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
