#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify a source-bound buffered RX using unchanged native aperture fixtures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
import fcntl
import hashlib
import itertools
import json
from threading import Event
from pathlib import Path

import characterize_rx_aperture as capture
from rx_aperture_evidence import sha, verify_witness
from rx_candidate_rc import captured_inputs
from spice_engine import engine, provenance
from spice_library import checked_netlist
from spice_slots import slot, reserved_slots

ROOT=Path(__file__).resolve().parents[1]
EXTRA=['rx_candidate_aperture.py','rx_candidate_rc.py','harden_rx_buffer4.py','rx_buffered_policy.py',
       'extract.py','reduce_rc.py','audit_rc.py','lvs_utils.py','digital_candidate_rc.py','physical_policy.py',
       'rx_aperture_evidence.py','spice_slots.py']


def extra_code():return {n:sha(ROOT/'scripts'/n) for n in EXTRA}


def audited_model(physical):
    physical=physical.resolve()
    if not physical.is_relative_to(ROOT/'build/diagnostics'):raise ValueError('Use an isolated RX physical artifact')
    manifest=captured_inputs(physical);info=json.loads((physical/'extraction.json').read_text())
    audit=json.loads((physical/'rc_audit.json').read_text());folder=ROOT/manifest['run']
    files=[physical/'summary.json',physical/'identity.json',physical/'config.json',physical/'extraction.json',
        physical/'rc_audit.json',folder/'final/nl/openlvds_ddr_rx.nl.v',folder/'final/gds/openlvds_ddr_rx.gds',
        folder/'final/spice/openlvds_ddr_rx.spice',physical/'rc_audit/reference.spice',ROOT/audit['report'],ROOT/info['netlist']]
    if not (audit['passed'] and audit['source_sha256']==info['source_sha256']==manifest['source_sha256'] and
            audit['gds_sha256']==info['gds_sha256']==sha(files[6]) and
            audit['netlist_sha256']==info['netlist_sha256'] and
            audit['report_sha256']==sha(ROOT/audit['report']) and
            audit['reference_sha256']==sha(physical/'rc_audit/reference.spice') and
            audit['physical_spice_sha256']==sha(folder/'final/spice/openlvds_ddr_rx.spice') and
            audit['producer_sha256']==sha(ROOT/'scripts/rx_candidate_rc.py')):
        raise ValueError('RX candidate lacks a current independent RC audit')
    checked_netlist(info)
    return info,{str(p.relative_to(ROOT)):sha(p) for p in files}


def seed_conditions():
    # Start with the publication cases that rejected the preceding driver.
    points=[('ss',40,200),('ss',0,200),('sf',40,200),('ss',0,20),('tt',0,200),('ff',0,200)]
    return [dict(process=p,temperature=t,edge='rising',polarity=polarity,clock_slew_ps=clock,
        data_slew_ps=20,kind='setup') for p,t,clock in points for polarity in ['rise','fall']]


def ordered_conditions(conditions):
    processes=['ss','sf','tt','fs','ff'];temperatures=[40,0,25]
    return sorted(conditions,key=lambda s:(processes.index(s['process']),temperatures.index(s['temperature']),
        -s['clock_slew_ps'],-s['data_slew_ps'],s['edge']!='rising',s['kind']!='setup',s['polarity']!='fall'))


def validate(root,manifest):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/characterization/rx_aperture'):raise ValueError('Use an isolated RX aperture artifact')
    capture.validate(root,manifest);identity=manifest['identity']
    if identity['requirements_sha256']!=sha(ROOT/'requirements.json') or identity['candidate_code']!=extra_code():
        raise ValueError('RX candidate requirements or producer changed')
    for n,value in dict(identity['code'],**identity['candidate_code']).items():
        if sha(root/n)!=value:raise ValueError('Captured RX aperture producer changed')
    info,reports=audited_model(ROOT/identity['physical'])
    if info!=identity['model'] or reports!=identity['physical_reports']:raise ValueError('RX physical proof changed')
    expected=capture.conditions(json.loads((root/'requirements.json').read_text()))
    if manifest['conditions']!=expected:raise ValueError('RX aperture coverage changed')


def prepare(physical):
    if engine()!='ngspice':raise ValueError('Use the pinned --ngspice environment')
    physical=physical.resolve();info,reports=audited_model(physical);lib=checked_netlist(info).encode()
    req=(ROOT/'requirements.json').read_bytes()
    identity=dict(code=capture.code_hashes(),candidate_code=extra_code(),simulator_provenance=provenance(),
        requirements_sha256=capture.sha(req),library_sha256=capture.sha(lib),model=info,
        period_ns=capture.PERIOD_NS,bracket_ps=list(capture.BRACKET_PS),resolution_ps=capture.RESOLUTION_PS,
        guard_ps=capture.GUARD_PS,physical=str(physical.relative_to(ROOT)),physical_reports=reports)
    root=ROOT/'build/characterization/rx_aperture'/capture.sha(json.dumps(identity,sort_keys=True).encode())[:16]
    if (root/'manifest.json').exists():validate(root,json.loads((root/'manifest.json').read_text()));return root
    root.mkdir(parents=True,exist_ok=True);(root/'library.spice').write_bytes(lib);(root/'requirements.json').write_bytes(req)
    for n in dict(identity['code'],**identity['candidate_code']):(root/n).write_bytes((ROOT/'scripts'/n).read_bytes())
    capture.atomic(root/'manifest.json',dict(identity=identity,conditions=capture.conditions(json.loads(req)),
        clock_mhz=410,supply_v=1.8,load_ff=20,qualified_phy=False))
    capture.atomic(root/'state.json',dict(status='prepared',qualified_phy=False));return root


def check_seeds(root,manifest):
    seeds=json.loads((root/'seed_summary.json').read_text())
    if not seeds.get('passed') or seeds['manifest_sha256']!=sha(root/'manifest.json'):
        raise ValueError('Loaded native RX endpoints have not passed')
    expected={capture.condition_id(s) for s in seed_conditions()}
    if set(seeds['cases'])!=expected:raise ValueError('Loaded native RX seed coverage changed')
    for spec in seed_conditions():
        name=capture.condition_id(spec);verify_witness(root,manifest,spec,800.,True)
        path=root/name/'point_800p000000/summary.json'
        if seeds['cases'][name]!=sha(path):raise ValueError('Loaded RX seed evidence changed')


def table(manifest,results,requirements,manifest_sha):
    expected=capture.conditions(requirements)
    if len(results)!=len(expected) or {capture.condition_id(r['spec']) for r in results}!={capture.condition_id(s) for s in expected}:
        raise ValueError('Need all 480 distinct RX aperture conditions')
    passed=all(r['passed'] for r in results);bounds={}
    for p,t in itertools.product(requirements['process_corners'],requirements['temperatures_c']):
        subset=[r for r in results if r['spec']['process']==p and r['spec']['temperature']==t]
        if len(subset)!=32 or not all(r['passed'] for r in subset):passed=False;continue
        bounds[f'{p}_{t}']={k+'_ps':max(r['bound_ps'] for r in subset if r['spec']['kind']==k) for k in ['setup','hold']}
    return dict(passed=passed,clock_mhz=410,load_ff=20,guard_ps=capture.GUARD_PS,resolution_ps=capture.RESOLUTION_PS,
        additional_link_margin_ps=requirements['minimum_sampling_margin_ps'],model_sha256=manifest['identity']['model']['netlist_sha256'],
        producer_code=manifest['identity']['code'],candidate_producer_code=manifest['identity']['candidate_code'],
        simulator_provenance=manifest['identity']['simulator_provenance'],manifest_sha256=manifest_sha,
        conditions=len(results),bounds=bounds,results=results,qualified_phy=False)


@contextmanager
def lease(wait_slot=None):
    if wait_slot is None:
        with slot():yield
        return
    if wait_slot not in range(reserved_slots(),6):raise ValueError('Requested slot is reserved or outside the six-slot budget')
    directory=ROOT/'build/diagnostics/spice_slots';directory.mkdir(parents=True,exist_ok=True)
    # Block in the kernel on one known short-running fixture's actual lease.
    # This avoids starvation behind a coordinator that immediately reacquires
    # free slots, without signalling or stopping any producer or simulator.
    with (directory/str(wait_slot)).open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        if wait_slot<reserved_slots():raise ValueError('Requested slot became reserved')
        yield


def run(root,jobs,stage,wait_slot=None):
    if wait_slot is not None and jobs!=1:raise ValueError('A blocking selected-slot wait requires one worker')
    root=root.resolve();manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if stage=='full':check_seeds(root,manifest)
        capture.atomic(root/'state.json',dict(status='running_'+stage,max_jobs=jobs,qualified_phy=False))
        conditions=seed_conditions() if stage=='endpoints' else ordered_conditions(manifest['conditions'])
        failed=Event()
        retained_endpoint_slot=wait_slot is not None and stage=='endpoints'
        def worker(spec):
            if failed.is_set():return dict(spec=spec,passed=False,held=True)
            validate(root,manifest)
            # Own one real global slot for each endpoint or complete boundary
            # search. The frozen legacy search itself does not acquire slots.
            with (nullcontext() if retained_endpoint_slot else lease(wait_slot)):
                if failed.is_set():return dict(spec=spec,passed=False,held=True)
                if stage=='endpoints':result=dict(spec=spec,passed=capture.point(root,manifest,spec,800.))
                else:result=capture.search(root,manifest,spec)
                if not result['passed']:failed.set()
            validate(root,manifest);return result
        with (lease(wait_slot) if retained_endpoint_slot else nullcontext()):
            with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(worker,conditions))
        validate(root,manifest)
        if stage=='endpoints':
            passed=all(r['passed'] for r in results)
            capture.atomic(root/'seed_summary.json',dict(passed=passed,qualified_phy=False,manifest_sha256=sha(root/'manifest.json'),
                cases={capture.condition_id(r['spec']):sha(root/capture.condition_id(r['spec'])/'point_800p000000/summary.json') for r in results if not r.get('held')},
                held_cases=[capture.condition_id(r['spec']) for r in results if r.get('held')]))
        elif any(r.get('held') for r in results):
            capture.atomic(root/'incomplete_summary.json',dict(passed=False,qualified_phy=False,manifest_sha256=sha(root/'manifest.json'),
                required_conditions=len(conditions),completed_conditions=sum(not r.get('held',False) for r in results),
                completed_results=[r for r in results if not r.get('held')],held_cases=[capture.condition_id(r['spec']) for r in results if r.get('held')]))
            capture.atomic(root/'state.json',dict(status='held_by_native_failure',passed=False,qualified_phy=False))
            return 1
        else:
            result=table(manifest,results,json.loads((root/'requirements.json').read_text()),sha(root/'manifest.json'))
            passed=result['passed'];capture.atomic(root/'table.json',result)
        capture.atomic(root/'state.json',dict(status='endpoints_complete' if stage=='endpoints' else 'complete',passed=passed,qualified_phy=False))
    return 0 if passed else 1


def dispatch(root,jobs,stage,wait_slot=None):
    if stage!='all':return run(root,jobs,stage,wait_slot)
    status=run(root,1,'endpoints',wait_slot)
    if status:return status
    # The completed six endpoint witnesses are rechecked by run(full). Full
    # boundary workers return to the shared pool rather than one selected slot.
    return run(root,jobs,'full')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('physical',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a.add_argument('--jobs',type=int,choices=[1,2,3],default=1);a.add_argument('--stage',choices=['endpoints','full','all'],default='endpoints');a.add_argument('--wait-slot',type=int,choices=range(6))
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.physical),flush=True)
    else:raise SystemExit(dispatch(a.artifact,a.jobs,a.stage,a.wait_slot))
