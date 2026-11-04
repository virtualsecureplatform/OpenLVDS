#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full fifteen-PVT native matrix for the actual repaired threshold loading."""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_phase_threshold_slew_v2 as pilot

ROOT=pilot.ROOT
base=pilot.base
VERSION='repaired-native-threshold-fifteen-pvt-v2.1'


def specifications(requirements):
    points=list(itertools.product(requirements['process_corners'],requirements['temperatures_c']))
    priority=[('ff',0),('fs',40),('sf',40),('tt',25),('ss',40)]
    points=[p for p in priority if p in points]+[p for p in points if p not in priority]
    return [dict(process=p,temperature=t,drive=1,swap=s,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf,
                 positive_offset=d,settle_ps=pilot.prefix.PREFIX_PS)
        for (p,t),(sr,sf),s,o,d in itertools.product(points,[(100,100),(20,250),(250,20)],[0,1],[-20,0,20],[0,1])]


def fixture(out,spec,devices):
    text=pilot.fixture(out,spec,devices)
    if text.count('" ss\n')!=1 or text.count('.options device temp=40\n')!=1:raise ValueError('Pilot PVT declaration changed')
    return text.replace('" ss\n','" '+spec['process']+'\n').replace('.options device temp=40\n',f'.options device temp={spec["temperature"]}\n')


def prepare(receipt):
    if not receipt.is_relative_to(ROOT/'build/diagnostics/phase_threshold_slew_verification_v2'):
        raise ValueError('Require the complete independently passing slew/order pilot')
    proof=json.loads((receipt/'summary.json').read_text());parent=ROOT/proof['identity']['artifact'];m=pilot.bound(parent)
    if (proof['cases']!=30 or proof['numerical_errors'] or proof['source_threshold_and_health_passed'] is not True
        or base.sha(parent/'manifest.json')!=proof['identity']['manifest_sha256']
        or base.sha(parent/'summary.json')!=proof['identity']['summary_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in proof['witness_files'].items())):raise ValueError('Pilot proof or witnesses changed')
    prefix=ROOT/m['identity']['parent'];pilot.prefix.bound(prefix)
    for name,value in m['libraries'].items():
        if base.sha(prefix/name)!=value:raise ValueError('Matched source prefix library differs')
    inputs=dict(proof['witness_files']);inputs[str((receipt/'summary.json').relative_to(ROOT))]=base.sha(receipt/'summary.json')
    inputs.update({str((parent/n).relative_to(ROOT)):base.sha(parent/n) for n in m['libraries']})
    paths=[Path(__file__),ROOT/'scripts/verify_phase_threshold_slew_v2.py',ROOT/'scripts/verify_phase_threshold_v2.py']
    code=dict(m['identity']['code']);code.update({str(p.relative_to(ROOT)):base.sha(p) for p in paths})
    specs=specifications(json.loads((ROOT/'requirements.json').read_text()))
    identity=dict(version=VERSION,code=code,inputs=inputs,parent=str(parent.relative_to(ROOT)),
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=base.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/phase_threshold_pvt_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in m['libraries']:base.write(out/name,(parent/name).read_text())
    tasks=[];devices=m['tasks'][0]['devices']
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();base.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=base.sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:base.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/phase_threshold_pvt_v2'):raise ValueError('Wrong threshold PVT context')
    m=pilot.prefix.parent_source.parent_source.parent_source.original_bound(out);i=m['identity']
    if (i['version']!=VERSION or base.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(base.sha(ROOT/n)!=v for n,v in i['inputs'].items())
        or [t['spec'] for t in m['tasks']]!=specifications(json.loads((ROOT/'requirements.json').read_text()))):
        raise ValueError('Threshold PVT coverage or inputs changed')
    return m


def measure(folder,spec):
    tasks=json.loads((folder.parent/'manifest.json').read_text())['tasks'];task=next(t for t in tasks if t['id']==folder.name)
    return dict(pilot.prefix.analysis.measure(folder,task),version=VERSION,
        scope='Fifteen-PVT static threshold/load source characterization; no route-update, physical, convergence or PHY admission')


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
