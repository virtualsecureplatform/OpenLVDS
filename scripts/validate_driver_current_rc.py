#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture one fresh driver RC comparison without issuing a six-case certificate."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

import qualify_driver_current_components as qualification
import validate_fast as validation
import rc_trace
from dll_campaign import atomic
from rc_fast import fast
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import engine, provenance
from spice_library import library, replace
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
TOP = 'openlvds_driver_core'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def device_signature(text):
    # Quick-node reduction may redistribute wire R and C; every other
    # statement, including PDK resistor/capacitor instances and ports, stays.
    lines = [line for line in text.splitlines() if line.strip() and
             not line.lstrip().startswith('*') and not line.split()[0].lower().startswith(('r','c'))]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


def component_gate(campaign):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/driver_components'):
        raise ValueError('Use the complete corrected-driver component campaign')
    manifest = json.loads((campaign/'manifest.json').read_text())
    qualification.component.check_coverage(manifest['tasks'], json.loads((ROOT/'requirements.json').read_text()))
    if not (campaign/'summary.json').is_file() or any(
            not (campaign/t['id']/'summary.json').is_file() for t in manifest['tasks']):
        raise ValueError('Complete all thirty original driver cases before RC comparison')
    report = json.loads((campaign/'summary.json').read_text())
    if report.get('required') != 30 or report.get('passed_cases') != 30 or report.get('passed') is not True:
        raise ValueError('Corrected-driver components failed')
    qualification.run(campaign, 1)  # All reports exist: cached remeasurement only.
    return manifest


def prepare(campaign):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice runtime')
    manifest = component_gate(campaign); previous = manifest['identity']
    comparison = ROOT/previous['comparison']
    cm = json.loads((comparison/'manifest.json').read_text())
    models, files, code = qualification.corrected.physical_models(
        {k: ROOT/v for k,v in cm['identity']['layouts'].items()})
    layout = ROOT/previous['layout']; info = json.loads((layout/'extraction.json').read_text())
    if cm['identity']['layouts']['restore_64_24'] != previous['layout']:
        raise ValueError('Components and native comparison select different drivers')
    native = models['restore_64_24']
    base, bias_inputs, _ = library(extracted=True, designs={'lvds_bias'})
    paths = files+[campaign/'manifest.json', campaign/'summary.json', comparison/'manifest.json',
        ROOT/'analog/openlvds.spice', ROOT/'requirements.json', ROOT/'build/extracted/current.json', ROOT/'build/layout/current.json']
    inputs = dict(previous['inputs'], **{str(p.relative_to(ROOT)):sha(p) for p in paths})
    names = set(previous['code'])|set(code)|{NAME,'validate_fast.py','rc_trace.py','rc_certificate.py',
        'rc_fast.py','spice_library.py','spice_scope.py','spice_dispatch.py'}
    identity = dict(campaign=str(campaign.relative_to(ROOT)), layout=str(layout.relative_to(ROOT)),
        inputs=inputs, code={n:sha(ROOT/'scripts'/n) for n in names},
        simulator_provenance=provenance(), max_tau_ps=.1,
        scope='Fresh driver-only full/quick-node RC comparison using the original complete 2560 ns TT25 fixture, exact shared bias, 20 ps edge/20 mV voltage tolerances and original trace attestation. One actual fair simulation lease at a time. No active model/catalog change and no complete six-case certificate or PHY admission.')
    out = ROOT/'build/diagnostics/driver_rc_comparison'/hashlib.sha256(
        json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        m = json.loads((out/'manifest.json').read_text())
        if m['identity'] != identity or any(sha(out/n)!=h for n,h in m['files'].items()):
            raise ValueError('Prepared driver RC comparison changed')
        return out
    metadata = fast(ROOT/info['netlist'],out/'driver.fast.spice',.1)
    reduced = (out/'driver.fast.spice').read_text()
    if metadata['source_sha256'] != info['netlist_sha256'] or device_signature(native) != device_signature(reduced):
        raise ValueError('Driver RC approximation changes a device, port or directive')
    texts = {mode:replace(base.decode(),TOP,text) for mode,text in [('full',native),('fast',reduced)]}
    if any(closure_hash(text,'lvds_bias') != closure_hash(base,'lvds_bias') for text in texts.values()):
        raise ValueError('Driver RC comparison changes the exact shared bias')
    for mode,text in texts.items():
        (out/(mode+'.library.spice')).write_text(text)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False,complete_suite=False,
        full_inputs=dict(bias_inputs, **{TOP:info['netlist_sha256']}),
        fast_inputs=dict(bias_inputs, **{TOP:metadata['fast_sha256']}),
        files={n:sha(out/n) for n in ['driver.fast.spice','driver.fast.json','full.library.spice','fast.library.spice']}))
    return out


@contextmanager
def profile(views):
    previous = validation.library, validation.slot
    try:
        validation.library = lambda **kwargs: (*views['fast' if kwargs.get('fast') else 'full'], {})
        validation.slot = lambda: lease(ROOT,priority=1,label='corrected_driver_fresh_rc')
        yield
    finally:
        validation.library,validation.slot = previous


def case_path(text,mode,stamp):
    body,nodes = validation.fixture('driver',{})
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    recipe = hashlib.sha256(json.dumps([body,nodes,'2560n','1n',str(pdk),validation.REQUIREMENTS_HASH]).encode()).hexdigest()
    scope = closure_hash(text,'openlvds_driver')
    return ROOT/'build/rc_validation'/engine()/'driver'/(mode+'_'+scope[:10]+'_'+stamp[:10]+'_'+recipe[:10])


def guard_trace(folder,scope,inputs,stamp):
    if not folder.exists():
        return
    evidence = rc_trace.verified(folder,engine(),stamp,validation.REQUIREMENTS_HASH)
    if evidence and evidence['scope_sha256']==scope and evidence['inputs']==inputs:
        return
    if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log','trace_evidence.json']):
        raise ValueError('Unattested or partial driver RC trace retained; do not overwrite or restart')


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_rc_comparison'):
        raise ValueError('Use a prepared isolated driver RC comparison')
    manifest=json.loads((out/'manifest.json').read_text());identity=manifest['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=identity['simulator_provenance'] or
                out.name!=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()) or
                any(sha(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()) or
                any(sha(out/n)!=h for n,h in manifest['files'].items())):
            raise ValueError('Driver RC comparison context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        views={mode:((out/(mode+'.library.spice')).read_bytes(),manifest[mode+'_inputs']) for mode in ['full','fast']}
        results=[]
        with profile(views):
            for mode in ['full','fast']:
                text,inputs=views[mode];folder=case_path(text,mode,identity['simulator_provenance'])
                guard_trace(folder,closure_hash(text,'openlvds_driver'),inputs,identity['simulator_provenance'])
                atomic(out/'state.json',dict(status='running_'+mode,artifact=str(folder.relative_to(ROOT)),qualified_phy=False))
                start=time.monotonic()
                result=validation.simulate('driver',mode=='fast',resume=True,simulator_stamp=identity['simulator_provenance'])
                unchanged()
                if result[2] is None or result[4].get('artifact')!=str(folder.relative_to(ROOT)):
                    raise ValueError('Driver RC reference failed or changed fixture generation')
                atomic(out/(mode+'_runtime.json'),dict(wall_seconds=time.monotonic()-start,artifact=result[4]['artifact']))
                results.append(result)
        comparison=validation.compare('driver',*results)
        report=dict(diagnostic_complete=True,qualified_phy=False,complete_suite=False,driver_rc_passed=comparison['passed'],
            manifest_sha256=stamp,case=comparison,reference_inputs=results[0][3],fast_inputs=results[1][3],
            missing_cases=sorted(validation.REQUIRED-{'driver'}),scope=identity['scope'])
        unchanged();capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed',driver_rc_passed=report['driver_rc_passed'],qualified_phy=False))
    return out/'summary.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('artifact',type=Path);args=parser.parse_args()
    print((prepare if args.action=='prepare' else run)(args.artifact.resolve()),flush=True)
