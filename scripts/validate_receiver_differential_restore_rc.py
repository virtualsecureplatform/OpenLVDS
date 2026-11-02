#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare admitted original differential-restoration receiver RC views after all sixty component cases."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path

import qualify_receiver_differential_restore as qualification
import validate_driver_current_rc as shared
import validate_fast as validation
from dll_campaign import atomic
from dll_candidate_library import audited
from rc_fast import fast
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import engine, provenance
from spice_library import checked_netlist, library, replace
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
KIND = 'receiver'
TOP = 'openlvds_receiver_core'
sha = shared.sha


def component_gate(campaign):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/receiver_components'):
        raise ValueError('Use the completed isolated original differential-restoration receiver components')
    m = json.loads((campaign/'manifest.json').read_text())
    qualification.components.check_coverage(m['tasks'],json.loads((ROOT/'requirements.json').read_text()))
    if not (campaign/'summary.json').is_file() or any(
            not (campaign/t['id']/'summary.json').is_file() for t in m['tasks']):
        raise ValueError('Complete all sixty original receiver cases before RC comparison')
    r = json.loads((campaign/'summary.json').read_text())
    if r.get('required') != 60 or r.get('passed_cases') != 60 or r.get('passed') is not True:
        raise ValueError('Receiver components must pass all sixty original conditions')
    # The selector rechecks native transport and every cached component. No
    # missing component can dispatch, because all reports were required above.
    with (campaign/'.rc_admission.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with (campaign/'.execution.lock').open('a+') as producer:
            fcntl.flock(producer,fcntl.LOCK_EX)
        qualification.run('run',campaign,jobs=1)
    return m


def physical_model(identity):
    replay = ROOT/identity['replay']; layout = ROOT/identity['layout']
    selected = qualification.selected(replay)
    if selected['layout'] != identity['layout']:
        raise ValueError('Receiver component and native replay geometry differ')
    report = json.loads((layout/'summary.json').read_text())
    info = json.loads((layout/'extraction.json').read_text())
    variant = selected['differential_restore_variant']
    expected = qualification.native.physical.clocks.source_variant((ROOT/'analog/openlvds.spice').read_text(),True,variant)
    if (not report['passed'] or (layout/'candidate.spice').read_text() != expected or
            sha(layout/'candidate.spice') != info['source_sha256']):
        raise ValueError('Receiver RC model differs from the admitted circuit')
    audit = audited(layout,info); gds = ROOT/report['designs'][TOP]['gds']
    if sha(gds) != info['gds_sha256']:
        raise ValueError('Receiver RC extraction GDS changed')
    paths = [layout/n for n in ['summary.json','candidate.spice','extraction.json','rc_audit.json']]
    paths += [gds,ROOT/info['netlist'],ROOT/audit['report'],replay/'manifest.json',replay/'summary.json']
    return layout, info, checked_netlist(info), paths, set(report['identity']['code'])


def prepare(campaign):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice runtime')
    m = component_gate(campaign); previous = m['identity']
    layout,info,native,paths,code = physical_model(previous)
    base,bias_inputs,_ = library(extracted=True,designs={'lvds_bias'})
    paths += [campaign/'manifest.json',campaign/'summary.json',ROOT/'analog/openlvds.spice',
        ROOT/'requirements.json',ROOT/'build/extracted/current.json',ROOT/'build/layout/current.json']
    names = set(previous['code']) | code | {NAME,'validate_driver_current_rc.py','validate_fast.py',
        'rc_trace.py','rc_certificate.py','rc_fast.py','spice_library.py','spice_scope.py','spice_dispatch.py'}
    identity = dict(campaign=str(campaign.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),
        inputs=dict(previous['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}),
        code={n:sha(ROOT/'scripts'/n) for n in names},simulator_provenance=provenance(),max_tau_ps=.1,
        scope='Admitted original differential-restoration native receiver full versus quick-node wire RC, exact shared bias, original complete 60 ns TT25 fixture and original 20 ps/20 mV comparison limits. All sixty source/native component conditions and full native clock transport required first. One actual fair SPICE lease at a time, no outer lease. RC case only; joint six-case certificate, aperture, coupled timing, final payloads and PHY admission remain required.')
    out = ROOT/'build/diagnostics/receiver_differential_restore_rc'/hashlib.sha256(
        json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').is_file():
        prior = json.loads((out/'manifest.json').read_text())
        if prior['identity'] != identity or any(sha(out/n) != h for n,h in prior['files'].items()):
            raise ValueError('Prepared receiver RC context changed')
        return out
    metadata = fast(ROOT/info['netlist'],out/'receiver.fast.spice',.1)
    reduced = (out/'receiver.fast.spice').read_text()
    if (metadata['source_sha256'] != info['netlist_sha256'] or
            shared.device_signature(native) != shared.device_signature(reduced)):
        raise ValueError('Receiver approximation changes a non-wire device, port or directive')
    for mode,text in [('full',native),('fast',reduced)]:
        view = replace(base.decode(),TOP,text)
        if closure_hash(view,'lvds_bias') != closure_hash(base,'lvds_bias'):
            raise ValueError('Receiver approximation changes the exact shared bias')
        p = out/(mode+'.library.spice')
        if p.exists() and p.read_text() != view:
            raise ValueError('Prepared receiver RC library changed')
        if not p.exists():
            p.write_text(view)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False,complete_suite=False,
        full_inputs=dict(bias_inputs,**{TOP:info['netlist_sha256']}),
        fast_inputs=dict(bias_inputs,**{TOP:metadata['fast_sha256']}),
        files={n:sha(out/n) for n in ['receiver.fast.spice','receiver.fast.json','full.library.spice','fast.library.spice']}))
    return out


@contextmanager
def profile(views):
    previous = validation.library,validation.slot
    try:
        validation.library = lambda **kwargs: (*views['fast' if kwargs.get('fast') else 'full'],{})
        validation.slot = lambda: lease(ROOT,priority=1,label='differential_restore_receiver_fresh_rc')
        yield
    finally:
        validation.library,validation.slot = previous


def case_path(text,mode,stamp):
    body,nodes = validation.fixture(KIND,{})
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    recipe = hashlib.sha256(json.dumps([body,nodes,'60n','100p',str(pdk),validation.REQUIREMENTS_HASH]).encode()).hexdigest()
    scope = closure_hash(text,validation.TOPS[KIND])
    return ROOT/'build/rc_validation'/engine()/KIND/(mode+'_'+scope[:10]+'_'+stamp[:10]+'_'+recipe[:10])


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_differential_restore_rc'):
        raise ValueError('Use the isolated admitted receiver RC comparison')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                out.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n) != h for n,h in i['inputs'].items()) or
                any(sha(ROOT/'scripts'/n) != h for n,h in i['code'].items()) or
                any(sha(out/n) != h for n,h in m['files'].items())):
            raise ValueError('Receiver RC comparison context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        views = {mode:((out/(mode+'.library.spice')).read_bytes(),m[mode+'_inputs']) for mode in ['full','fast']}
        results = []
        with profile(views):
            for mode in ['full','fast']:
                text,inputs = views[mode]; folder = case_path(text,mode,i['simulator_provenance'])
                shared.guard_trace(folder,closure_hash(text,validation.TOPS[KIND]),inputs,i['simulator_provenance'])
                atomic(out/'state.json',dict(status='running_'+mode,artifact=str(folder.relative_to(ROOT)),qualified_phy=False))
                result = validation.simulate(KIND,mode=='fast',resume=True,simulator_stamp=i['simulator_provenance'])
                unchanged()
                if result[2] is None or result[4].get('artifact') != str(folder.relative_to(ROOT)):
                    raise ValueError('Receiver RC trace failed or changed its original fixture')
                results.append(result)
        compared = validation.compare(KIND,*results)
        report = dict(diagnostic_complete=True,qualified_phy=False,complete_suite=False,receiver_rc_passed=compared['passed'],
            manifest_sha256=stamp,case=compared,reference_inputs=results[0][3],fast_inputs=results[1][3],
            missing_cases=sorted(validation.REQUIRED-{KIND}),scope=i['scope'])
        unchanged(); capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed',receiver_rc_passed=report['receiver_rc_passed'],qualified_phy=False))
    return out/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['prepare','run'])
    p.add_argument('artifact',type=Path); a = p.parse_args()
    print((prepare if a.action=='prepare' else run)(a.artifact.resolve()),flush=True)
