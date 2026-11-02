#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Original receiver RC comparison after new spec admission and all sixty components."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import qualify_receiver_spec as qualification
import validate_receiver_tia_restore_rc as original
from dll_campaign import atomic
from rc_fast import fast
from receiver_static_diagnosis import capture_manifest
from spice_engine import engine,provenance
from spice_library import library,replace
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
sha=original.sha


def component_gate(campaign):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/receiver_components'):raise ValueError('Use specification-admitted receiver components')
    m=json.loads((campaign/'manifest.json').read_text());req=json.loads((ROOT/'requirements.json').read_text())
    qualification.components.check_coverage(m['tasks'],req)
    paths=[campaign/'summary.json',campaign/'spec_admission.json']
    paths += [campaign/t['id']/n for t in m['tasks'] for n in ['summary.json','bench.cir.prn']]
    if any(not p.is_file() for p in paths):raise ValueError('Complete all sixty specification-admitted component cases before RC comparison')
    report_stamp=sha(campaign/'summary.json');r=json.loads((campaign/'summary.json').read_text())
    if (r.get('passed') is not True or r.get('required')!=60 or r.get('passed_cases')!=60 or
            r.get('manifest_sha256')!=sha(campaign/'manifest.json')):raise ValueError('All sixty receiver components must pass')
    # Detect missing/changed cached outputs before invoking a scientific cached
    # recheck. An admission check must not dispatch an unfinished component.
    for task in m['tasks']:
        folder=campaign/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row.get('passed') is not True or row.get('manifest_sha256')!=sha(campaign/'manifest.json') or
                row.get('waveform_sha256')!=sha(folder/'bench.cir.prn') or
                any(sha(folder/n)!=h for n,h in task['files'].items())):raise ValueError('Completed receiver component proof changed')
    with (campaign/'.spec_rc_admission.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        qualification.run(campaign,jobs=1)  # All sixty complete: cached remeasurement only.
    if sha(campaign/'summary.json')!=report_stamp:raise ValueError('Component aggregate changed')
    proof=json.loads((campaign/'spec_admission.json').read_text())
    return m,proof


def prepare(campaign):
    if engine()!='ngspice':raise ValueError('Use pinned ngspice runtime')
    m,admission=component_gate(campaign);previous=m['identity']
    layout,info,native,paths,code=original.physical_model(previous)
    base,bias_inputs,_=library(extracted=True,designs={'lvds_bias'})
    paths += [campaign/'manifest.json',campaign/'summary.json',campaign/'spec_admission.json',ROOT/'analog/openlvds.spice',
              ROOT/'requirements.json',ROOT/'receiver_acceptance.json',ROOT/'build/extracted/current.json',ROOT/'build/layout/current.json']
    names=set(previous['code'])|code|set(qualification.screen.CODE)|{NAME,'qualify_receiver_spec.py','validate_receiver_tia_restore_rc.py',
        'validate_driver_current_rc.py','validate_fast.py','rc_trace.py','rc_certificate.py','rc_fast.py','spice_library.py','spice_scope.py','spice_dispatch.py'}
    identity=dict(campaign=str(campaign.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),screen=admission['screen'],
        inputs={**previous['inputs'],**admission['proofs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        code={n:sha(ROOT/'scripts'/n) for n in names},simulator_provenance=provenance(),max_tau_ps=.1,
        scope='Fresh specification admission and all sixty original receiver components before full/fast wire RC comparison. Exact shared bias, original complete 60 ns TT25 fixture and unchanged 20 ps/20 mV comparison limits. Legacy replay remains diagnostic and is never rewritten. RC case only; joint six-case certificate, aperture, coupled timing, long payloads and PHY release remain required.')
    out=ROOT/'build/diagnostics/receiver_spec_rc'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        old=json.loads((out/'manifest.json').read_text())
        if old['identity']!=identity or any(sha(out/n)!=h for n,h in old['files'].items()):raise ValueError('Prepared specification RC context changed')
        return out
    metadata=fast(ROOT/info['netlist'],out/'receiver.fast.spice',.1);reduced=(out/'receiver.fast.spice').read_text()
    if metadata['source_sha256']!=info['netlist_sha256'] or original.shared.device_signature(native)!=original.shared.device_signature(reduced):raise ValueError('Receiver approximation changed non-wire statements')
    for mode,text in [('full',native),('fast',reduced)]:
        view=replace(base.decode(),original.TOP,text)
        if closure_hash(view,'lvds_bias')!=closure_hash(base,'lvds_bias'):raise ValueError('Receiver approximation changed exact bias')
        p=out/(mode+'.library.spice')
        if p.exists() and p.read_text()!=view:raise ValueError('Prepared RC view changed')
        if not p.exists():p.write_text(view)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False,complete_suite=False,
        full_inputs={**bias_inputs,original.TOP:info['netlist_sha256']},fast_inputs={**bias_inputs,original.TOP:metadata['fast_sha256']},
        files={n:sha(out/n) for n in ['receiver.fast.spice','receiver.fast.json','full.library.spice','fast.library.spice']}))
    return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_spec_rc'):raise ValueError('Use prepared specification-admitted RC comparison')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator_provenance'] or
                out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
                any(sha(out/n)!=h for n,h in m['files'].items())):raise ValueError('Specification RC comparison changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        views={mode:((out/(mode+'.library.spice')).read_bytes(),m[mode+'_inputs']) for mode in ['full','fast']};results=[]
        with original.profile(views):
            for mode in ['full','fast']:
                text,inputs=views[mode];folder=original.case_path(text,mode,i['simulator_provenance'])
                original.shared.guard_trace(folder,closure_hash(text,original.validation.TOPS['receiver']),inputs,i['simulator_provenance'])
                atomic(out/'state.json',dict(status='running_'+mode,artifact=str(folder.relative_to(ROOT)),qualified_phy=False))
                result=original.validation.simulate('receiver',mode=='fast',resume=True,simulator_stamp=i['simulator_provenance']);unchanged()
                if result[2] is None or result[4].get('artifact')!=str(folder.relative_to(ROOT)):raise ValueError('Receiver RC trace incomplete or changed')
                results.append(result)
        compared=original.validation.compare('receiver',*results)
        report=dict(diagnostic_complete=True,qualified_phy=False,complete_suite=False,receiver_rc_passed=compared['passed'],manifest_sha256=stamp,
            case=compared,reference_inputs=results[0][3],fast_inputs=results[1][3],missing_cases=sorted(original.validation.REQUIRED-{'receiver'}),scope=i['scope'])
        unchanged();capture_manifest(out/'summary.json',report);atomic(out/'state.json',dict(status='completed',receiver_rc_passed=report['receiver_rc_passed'],qualified_phy=False))
    return out/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    print((prepare if a.action=='prepare' else run)(a.artifact.resolve()),flush=True)
