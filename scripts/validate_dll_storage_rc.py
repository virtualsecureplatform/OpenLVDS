#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare corrected DLL RC views only after the complete native screen passes."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path

import measure_dll_storage_stability as admission
import validate_driver_current_rc as shared
import validate_fast as validation
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import engine, provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
KIND = 'dll'
sha = shared.sha


def screen_gate(qualification):
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use the corrected isolated DLL qualification')
    m = json.loads((qualification/'manifest.json').read_text())
    tasks = [t for t in m['tasks'] if admission.storage.native.screen_task(t)]
    if (len(tasks) != 24 or not (qualification/'screen_summary.json').is_file() or
            any(not (qualification/t['id']/'summary.json').is_file() for t in tasks)):
        raise ValueError('Complete all twenty-four native screen cases before DLL RC comparison')
    # All native/source reports exist before the unchanged cached producer
    # is invoked. The comparison cannot dispatch a missing prerequisite.
    with (qualification/'.rc_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        checked, corners = admission.admitted(qualification)
    if checked != m or corners != [('ss',0),('tt',25),('ff',0)]:
        raise ValueError('Corrected native DLL screen binding changed')
    paths = [qualification/n for n in ['manifest.json', 'requirements.json',
        'storage_source_admission.json', 'screen_summary.json', 'full.spice', 'fast.spice']]
    for t in tasks:
        paths.extend(qualification/t['id']/n for n in ['summary.json', 'bench.cir', 'bench.cir.prn'])
    source = json.loads((qualification/'storage_source_admission.json').read_text())
    proofs = dict(source['proofs'], **m['identity']['full_models']['physical_reports'])
    proofs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    return m, proofs


def checked_views(qualification, identity):
    views = {mode: ((qualification/(mode+'.spice')).read_bytes(),
                   identity[mode+'_models']['inputs']) for mode in ['full','fast']}
    if any(set(inputs) != validation.MODELS[KIND] for _,inputs in views.values()):
        raise ValueError('DLL RC comparison requires exactly the declared three model inputs')
    if (views['full'][1]['lvds_bias'] != views['fast'][1]['lvds_bias'] or
            closure_hash(views['full'][0], 'lvds_bias') != closure_hash(views['fast'][0], 'lvds_bias')):
        raise ValueError('DLL RC comparison changes the exact shared bias')
    if shared.device_signature(views['full'][0].decode()) != shared.device_signature(views['fast'][0].decode()):
        raise ValueError('DLL approximation changes a non-wire device, port or directive')
    body, nodes = validation.fixture(KIND, {})
    for text,_ in views.values():
        ProbeNetwork(text.decode()).validate(body, nodes)
    return views


def prepare(qualification):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice runtime')
    m, proofs = screen_gate(qualification); previous = m['identity']
    views = checked_views(qualification, previous)
    names = set(previous['code']) | set(admission.PRODUCERS) | {NAME,
        'measure_dll_storage_stability.py', 'validate_driver_current_rc.py',
        'validate_fast.py', 'rc_trace.py', 'rc_certificate.py', 'spice_probes.py',
        'spice_scope.py', 'spice_dispatch.py', 'receiver_static_diagnosis.py'}
    identity = dict(qualification=str(qualification.relative_to(ROOT)), inputs=proofs,
        code={n: sha(ROOT/'scripts'/n) for n in names}, simulator_provenance=provenance(),
        scope='Corrected 16 pF native DLL/PFD full versus quick-node RC views, exact shared bias, original full 1500 ns TT25 fixture and original 20 ps/20 mV limits. Complete 24-case native screen prerequisite. One actual fair SPICE lease at a time; no outer lease. RC comparison only: measured stability, full native qualification, joint six-case certificate and PHY admission remain required.')
    out = ROOT/'build/diagnostics/dll_storage_rc_comparison'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    for mode,(text,_) in views.items():
        p = out/(mode+'.library.spice')
        if p.exists() and p.read_bytes() != text:
            raise ValueError('Prepared DLL RC library changed')
        if not p.exists():
            p.write_bytes(text)
    capture_manifest(out/'manifest.json', dict(identity=identity, qualified_phy=False, complete_suite=False,
        full_inputs=views['full'][1], fast_inputs=views['fast'][1],
        files={mode+'.library.spice': sha(out/(mode+'.library.spice')) for mode in views}))
    return out


@contextmanager
def profile(views):
    previous = validation.library, validation.slot
    try:
        validation.library = lambda **kwargs: (*views['fast' if kwargs.get('fast') else 'full'], {})
        validation.slot = lambda: lease(ROOT, priority=1, label='corrected_dll_fresh_rc')
        yield
    finally:
        validation.library, validation.slot = previous


def case_path(text, mode, stamp):
    body, nodes = validation.fixture(KIND, {})
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    recipe = hashlib.sha256(json.dumps([body,nodes,'1500n','100p',str(pdk),validation.REQUIREMENTS_HASH]).encode()).hexdigest()
    scope = closure_hash(text, validation.TOPS[KIND])
    return ROOT/'build/rc_validation'/engine()/KIND/(mode+'_'+scope[:10]+'_'+stamp[:10]+'_'+recipe[:10])


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dll_storage_rc_comparison'):
        raise ValueError('Use the prepared isolated DLL RC comparison')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                out.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n) != h for n,h in i['inputs'].items()) or
                any(sha(ROOT/'scripts'/n) != h for n,h in i['code'].items()) or
                any(sha(out/n) != h for n,h in m['files'].items())):
            raise ValueError('DLL RC comparison context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        views = {mode: ((out/(mode+'.library.spice')).read_bytes(), m[mode+'_inputs']) for mode in ['full','fast']}
        results = []
        with profile(views):
            for mode in ['full','fast']:
                text,inputs = views[mode]; folder = case_path(text,mode,i['simulator_provenance'])
                shared.guard_trace(folder,closure_hash(text,validation.TOPS[KIND]),inputs,i['simulator_provenance'])
                atomic(out/'state.json',dict(status='running_'+mode,artifact=str(folder.relative_to(ROOT)),qualified_phy=False))
                result = validation.simulate(KIND,mode=='fast',resume=True,simulator_stamp=i['simulator_provenance'])
                unchanged()
                if result[2] is None or result[4].get('artifact') != str(folder.relative_to(ROOT)):
                    raise ValueError('DLL RC reference failed or differs from its original fixture')
                results.append(result)
        compared = validation.compare(KIND,*results)
        report = dict(diagnostic_complete=True,qualified_phy=False,complete_suite=False,dll_rc_passed=compared['passed'],
            manifest_sha256=stamp,case=compared,reference_inputs=results[0][3],fast_inputs=results[1][3],
            missing_cases=sorted(validation.REQUIRED-{KIND}),scope=i['scope'])
        unchanged(); capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed',dll_rc_passed=report['dll_rc_passed'],qualified_phy=False))
    return out/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['prepare','run'])
    p.add_argument('artifact',type=Path); a = p.parse_args()
    print((prepare if a.action=='prepare' else run)(a.artifact.resolve()),flush=True)
