#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Require verified PVT controls before source generation and physical PFD runs."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

import harden_slew_pfd as physical

ROOT=Path(__file__).resolve().parents[1]
PROFILE='source-slew-with-controls-v1'
sha=physical.sha


def controls_gate(controls):
    import qualify_slew_frontend_controls as control
    if not controls.is_relative_to(ROOT/'build/diagnostics'/control.NAMESPACE):raise ValueError('Require the source-control qualification artifact')
    with (controls/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=control.verify(controls)
        if not report['source_controls_passed'] or not report['ranked_survivors']:
            raise ValueError('Passing all-PVT reset/disable controls are required before physical source')
        m=control.bound(controls)
    return m,report


def prepare(controls):
    import qualify_slew_frontend_controls as control
    import prepare_slew_pfd as original
    cm,r=controls_gate(controls);parent=ROOT/cm['identity']['parent']
    er=json.loads((parent/'summary.json').read_text())
    winner=r['ranked_survivors'][0]
    source=next(c for c in er['candidates'] if c['variant']==winner and c['passed'])
    # Retain the source ranking among candidates which also passed controls.
    if r['ranked_survivors']!=[v for v in er['ranked_survivors'] if v in r['ranked_survivors']]:
        raise ValueError('Control admission changed the measured source ranking')
    inputs=dict(cm['identity']['inputs']);code=dict(cm['identity']['code'])
    paths=[controls/n for n in ('manifest.json','summary.json')]
    for t in cm['tasks']:paths += [controls/t['id']/n for n in (*control.OUTPUTS,'summary.json','bench.cir')]
    paths += [ROOT/'sky130/experiments/lvds_pfd_area_fast_reset.v',ROOT/'sky130/pfd_blackboxes.v',ROOT/'constraints/pfd.sdc',
              ROOT/'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v']
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    for n in (Path(__file__).name,'prepare_slew_pfd.py','pfd_slew_policy.py','pfd_fast_reset_policy.py','physical_policy.py'):
        code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=str(parent.relative_to(ROOT)),controls=str(controls.relative_to(ROOT)),admission_profile=PROFILE,
                  variant=winner,coverage_recipe=dict(version=control.expansion.coverage.VERSION,worst_screened_pvt=source['worst_screened_pvt']),
                  inputs=inputs,code=code,policy='pulse-area-fast-reset-slew-v1',
                  scope='Source timing and all-PVT reset/disable-qualified frontend, encoded as preserved named cells. Physical matching, DRC/LVS/RC, expanded native/loop/stability/stress and PHY qualification remain required.')
    out=ROOT/'build/diagnostics/slew_pfd_source'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        generated={'lvds_pfd.v':original.policy.source((ROOT/'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text(),winner),
                   'slew_blackboxes.v':original.policy.blackboxes(winner),'pfd_blackboxes.v':(ROOT/'sky130/pfd_blackboxes.v').read_text(),
                   'pfd.sdc':(ROOT/'constraints/pfd.sdc').read_text()}
        for n,text in generated.items():physical.write_once(out/n,text)
        physical.capture_manifest(out/'manifest.json',dict(identity=identity,files={n:sha(out/n) for n in generated},qualified_phy=False,physical_admission=False))
    return out


def bound(out):
    import prepare_slew_pfd as original
    m=original.bound(out);i=m['identity']
    if i.get('admission_profile')!=PROFILE or not i.get('controls'):
        raise ValueError('Require the source timing plus control admission profile')
    cm,r=controls_gate(ROOT/i['controls'])
    source_report=json.loads((ROOT/cm['identity']['parent']/'summary.json').read_text())
    winner=next(c for c in source_report['candidates'] if c['variant']==i['variant'] and c['passed'])
    expected_recipe=dict(version='dll-slew-repair-v1',worst_screened_pvt=winner['worst_screened_pvt'])
    if (i['parent']!=cm['identity']['parent'] or i['variant']!=r['ranked_survivors'][0] or
        i['coverage_recipe']!=expected_recipe or i['code'].get(Path(__file__).name)!=sha(Path(__file__))):raise ValueError('Controlled source admission changed')
    return m


@contextmanager
def physical_profile():
    previous=physical.source_gate
    def gate(parent):
        if not parent.is_relative_to(ROOT/'build/diagnostics/slew_pfd_source'):raise ValueError('Require controlled source artifact')
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
        p=subprocess.run(['/usr/bin/python3',str(Path(__file__)),'bound',str(parent)],cwd=ROOT,env=env,capture_output=True,text=True)
        if p.returncode:raise ValueError('Controlled source validation failed: '+p.stderr[-2000:])
        return json.loads(p.stdout)
    try:
        physical.source_gate=gate;yield
    finally:physical.source_gate=previous


def prepare_physical(source,baseline):
    with physical_profile():return physical.prepare(source,baseline)


def physical_context(out):
    m=physical.bound(out)
    with physical_profile():physical.source_gate(ROOT/m['identity']['parent'])
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['source','bound','physical','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--baseline',type=Path)
    a=p.parse_args();artifact=a.artifact.resolve()
    if a.action=='source':result=prepare(artifact)
    elif a.action=='bound':result=bound(artifact)
    elif a.action=='physical':
        if not a.baseline:p.error('--baseline required')
        result=prepare_physical(artifact,a.baseline.resolve())
    else:
        physical_context(artifact);result=getattr(physical,a.action)(artifact)
    print(result if a.action in ('source','physical') else json.dumps(result,indent=2),flush=True)
