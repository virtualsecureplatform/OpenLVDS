#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the repaired signed threshold through both orders and 250 ps slew.

Use the independently paired 20 ns simulation prefix. Retain the physical
conditioner, base/fine MIM geometry, voltage, precision and health limits.
The earlier six matched-slew, swap-0 cases remain independent evidence; this
cohort supplies the other 30 SS40 combinations before an all-PVT expansion.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_phase_prefix_v2 as prefix

base=prefix.base
ROOT=prefix.ROOT
VERSION='native-threshold-repaired-slew-order-pilot-v2.1'


def specifications():
    return [dict(drive=1,swap=s,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf,
                 positive_offset=d,settle_ps=prefix.PREFIX_PS)
        for (sr,sf),s,o,d in itertools.product([(100,100),(20,250),(250,20)],[0,1],[-20,0,20],[0,1])
        if (sr,sf,s)!=(100,100,0)]


def fixture(out,spec,devices):return prefix.fixture(out,spec,devices)


def prepare(receipt):
    if not receipt.is_relative_to(ROOT/'build/diagnostics/phase_prefix_verification_v2'):
        raise ValueError('Require independent prefix equivalence')
    proof=json.loads((receipt/'summary.json').read_text());parent=ROOT/proof['identity']['artifact'];m=prefix.bound(parent)
    if (proof['equivalence_passed'] is not True or proof['cases']!=6
        or base.sha(parent/'manifest.json')!=proof['identity']['manifest_sha256']
        or base.sha(parent/'summary.json')!=proof['identity']['summary_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in proof['witness_files'].items())):
        raise ValueError('Prefix proof or native witnesses changed')
    files=[Path(__file__),Path(prefix.__file__),Path(prefix.analysis.__file__),
        ROOT/'scripts/probe_phase_threshold_load_v2.py',ROOT/'scripts/probe_phase_threshold_v2.py',
        ROOT/'scripts/phase_threshold_pair_v2.py',ROOT/'scripts/probe_arbiter_reference_cap_v2.py',
        ROOT/'scripts/probe_analog_conditioned_arbiter_v2.py',ROOT/'scripts/probe_tag_arbiter_v2.py',
        ROOT/'scripts/dll_analog_frontend_v2_tailtrim.py',ROOT/'scripts/dll_analog_frontend_v2_fingered.py',
        ROOT/'scripts/dll_analog_frontend_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    inputs=dict(proof['witness_files']);inputs[str((receipt/'summary.json').relative_to(ROOT))]=base.sha(receipt/'summary.json')
    inputs.update({str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in ['manifest.json','summary.json','state.json']})
    specs=specifications()
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):base.sha(p) for p in files},inputs=inputs,
        parent=str(parent.relative_to(ROOT)),pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],
        model_library=m['identity']['model_library'],model_library_sha256=m['identity']['model_library_sha256'],
        simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/phase_threshold_slew_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in ['cells.spice','frontend.spice','bias.spice','arbiter.spice','threshold.spice']:base.write(out/name,(parent/name).read_text())
    tasks=[];devices=m['tasks'][0]['devices']
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/phase_threshold_slew_v2'):raise ValueError('Wrong threshold slew context')
    m=prefix.parent_source.parent_source.parent_source.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['inputs'].items()) or [t['spec'] for t in m['tasks']]!=specifications()):
        raise ValueError('Threshold slew inputs or coverage changed')
    return m


def measure(folder,spec):
    tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks'];task=next(t for t in tasks if t['id']==folder.name)
    return dict(prefix.analysis.measure(folder,task),version=VERSION,
        scope='SS40 repaired-threshold both-order/slew source diagnostic only; no all-PVT, route update, physical or DLL admission')


@contextmanager
def profile():
    before=base.bound,base.measure;base.bound=bound;base.measure=measure
    try:yield
    finally:base.bound,base.measure=before


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():base.run(a.artifact.resolve())
