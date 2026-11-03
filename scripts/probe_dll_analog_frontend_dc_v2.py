#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure the always-biased analog revision after the failed v1 DC grid.

The unchanged DC engine runs under an isolated revision profile, with every
producer captured before artifact creation. Both stages' tails are checked;
the original limits and original failed experiment remain unchanged.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import dll_analog_frontend_v2 as policy
import probe_dll_analog_frontend_dc as dc
from expand_dll_slew_frontends import write_once
from receiver_static_diagnosis import capture_manifest
from spice_engine import engine,provenance

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_dc_v2'
sha=dc.sha
OUTPUTS=dc.OUTPUTS


def failed_context(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics'/dc.NAMESPACE):raise ValueError('Require the retained complete first analog DC grid')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=dc.verify(parent);m=dc.bound(parent)
    if report['dc_ready_variants'] or m['identity']['policy']!='dll-analog-frontend-v1':raise ValueError('Use the failed original analog architecture as the revision prerequisite')
    return m


def measurements(values,task):
    if not all(np.isfinite(v) for v in values.values()):raise ValueError('Nonfinite revised analog operating point')
    def voltage(node):return 0. if node=='0' else float(values['v('+node.replace(':','.').lower()+')'])
    def parameter(name,vector):
        field=name.rsplit('_',1)[-1];keys=[vector]
        if field in ('id','vdsat'):keys += [('i' if field=='id' else 'v')+'('+vector+')']
        found=[float(values[k]) for k in keys if k in values]
        if not found or any(v!=found[0] for v in found):raise ValueError('Missing or inconsistent revised model vector: '+name)
        return found[0]
    params={n:parameter(n,v) for n,v in policy.op_parameters().items()}
    if (abs(voltage('REF')-task['ref_v'])>1e-8 or abs(voltage('FDB')-task['fb_v'])>1e-8 or
        abs(voltage('VDDIO')-3.3)>1e-8 or abs(voltage('VDDD')-1.8)>1e-8):raise ValueError('Revised analog DC signal or fixed rail changed')
    target=policy.VARIANTS[task['variant']]['tail_ua']*1e-6;refs={}
    for name in ('n_reference','p_reference'):
        p={k:params[name+'_'+k] for k in ('id','gm','gds','vdsat')};current=abs(p['id'])
        p.update(drain_current_magnitude_a=current,passed=bool(.75*target<=current<=1.25*target and abs(p['gm'])>0))
        refs[name]=p
    ref_match=.8*refs['n_reference']['drain_current_magnitude_a']<=refs['p_reference']['drain_current_magnitude_a']<=1.2*refs['n_reference']['drain_current_magnitude_a']
    tails={}
    for name,role in policy.tail_roles().items():
        p={k:params[name+'_'+k] for k in ('id','gm','gds','vdsat')}
        vds=voltage(role['node']) if role['polarity']=='n' else voltage('VDDD')-voltage(role['node'])
        saturation=abs(p['vdsat']);current=abs(p['id']);ref=refs[role['reference']]['drain_current_magnitude_a']
        margin=vds-saturation
        p.update(drain_current_magnitude_a=current,forward_vds_v=vds,headroom_v=margin,polarity=role['polarity'],
                 passed=bool(margin>=.02 and saturation>0 and abs(p['gm'])>0 and p['gds']>=0 and
                             .75*target<=current<=1.25*target and .8*ref<=current<=1.2*ref))
        tails[name]=p
    outputs={}
    for side,node,signal in [('ref','REF_FAST',task['ref_v']),('fb','FDB_FAST',task['fb_v'])]:
        value=voltage(node);outputs[side]=dict(voltage_v=value,expected_high=signal>.9 if signal!=.9 else None,
            passed=bool(signal==.9 or (value<.36 if signal==0 else value>1.44)))
    stress=[]
    for device in policy.circuit(task['variant'])[1]:
        volts=[voltage(n) for n in device['terminals']];worst=max(abs(a-b) for a,b in itertools.combinations(volts,2))
        limit=5.5 if device['model']==policy.P5 else 1.95
        stress.append(dict(device=device['name'],max_terminal_difference_v=worst,limit_v=limit,passed=bool(worst<=limit)))
    common=voltage('XF:VCM');common_ok=abs(common-.9)<=.01
    passed=bool(common_ok and ref_match and all(r['passed'] for r in refs.values()) and all(t['passed'] for t in tails.values()) and
                all(o['passed'] for o in outputs.values()) and all(s['passed'] for s in stress))
    return dict(passed=passed,references=refs,reference_matching_passed=bool(ref_match),tails=tails,outputs=outputs,
                common_mode_v=common,common_mode_passed=common_ok,stress=stress,
                rail_power_w=float(-3.3*values['i(va)']-1.8*values['i(vd)']))


@contextmanager
def profile():
    previous=dc.policy,dc.NAMESPACE,dc.measurements
    try:
        dc.policy=policy;dc.NAMESPACE=NAMESPACE;dc.measurements=measurements
        yield
    finally:dc.policy,dc.NAMESPACE,dc.measurements=previous


def prepare(failed):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice environment')
    pm=failed_context(failed);pi=pm['identity'];q=ROOT/pi['qualification_reference']
    inputs=dict(pi['inputs']);paths=[failed/n for n in ('manifest.json','summary.json',*pm['libraries'])]
    for t in pm['tasks']:paths += [failed/t['id']/n for n in (*OUTPUTS,'summary.json','bench.cir')]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pi['code'])
    for n in (Path(__file__).name,'dll_analog_frontend_v2.py'):code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=pi['parent'],failed_revision=str(failed.relative_to(ROOT)),qualification_reference=pi['qualification_reference'],
                  policy=policy.VERSION,simulator=provenance(),inputs=inputs,code=code,pdk=pi['pdk'],
                  scope='Revision after measured rail-state tail cutoff: resistor-loaded NMOS preamplifiers, divided drain taps, PMOS differential decision stages, two shared local biases. Four original current/input-width variants, twenty SS40 fixed-rail DC points. Both stages and all MOS terminal stresses checked. No timing, physical, PVT or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);native=(q/'full.spice').read_text()
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);libraries={};prepared=[]
        for v in policy.VARIANTS:
            write_once(out/(v+'.spice'),native+policy.circuit(v)[0]);libraries[v+'.spice']=sha(out/(v+'.spice'))
        with profile():
            for t in dc.tasks():
                folder=out/t['id'];folder.mkdir(exist_ok=True)
                deck,nodes=dc.fixture(t,out,Path(pi['pdk']['path']),(out/(t['variant']+'.spice')).read_text())
                write_once(folder/'bench.cir',deck);prepared.append(dict(t,voltage_nodes=nodes,deck_sha256=sha(folder/'bench.cir')))
        (out/'producers').mkdir(exist_ok=True)
        for n in code:write_once(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,libraries=libraries,tasks=prepared,physical_admission=False,qualified_phy=False))
    return out


def admission(out):
    if not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE):raise ValueError('Require the revised analog DC artifact')
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    old=failed_context(ROOT/i['failed_revision'])
    if i['policy']!=policy.VERSION or i['parent']!=old['identity']['parent'] or i['qualification_reference']!=old['identity']['qualification_reference']:
        raise ValueError('Revised analog DC prerequisite changed')


def bound(out):
    admission(out)
    with profile():return dc.bound(out)


def run(out):
    admission(out)
    with profile():return dc.run(out)


def verify(out):
    admission(out)
    with profile():return dc.verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','bound','run','verify']);p.add_argument('artifact',type=Path)
    a=p.parse_args();r=globals()[a.action](a.artifact.resolve());print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
