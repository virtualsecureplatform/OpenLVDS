#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently qualify one complete static-counter variant for joint tests.

Other declared variants may still run. Bind only immutable completed files;
this receipt covers both duties/stopped levels for one SS40 counter profile,
not the full producer matrix, full PVT, controller routing or PHY admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import verify_static_phase_clock_release_v5 as verification
from native_binary_raw_v2 import validate

ROOT=verification.ROOT
sha=verification.sha
VERSION='independent-complete-static-phase-profile-preselection-v2.1'


def verify(parent,variant):
    m=verification.pilot.bound(parent);devices=verification.regenerate(parent,m)
    selected=[t for t in m['tasks'] if t['spec']['variant']==variant]
    expected=[s for s in verification.pilot.specifications() if s['variant']==variant]
    if len(selected)!=4 or [t['spec'] for t in selected]!=expected:raise ValueError('Require both duties and both stopped levels')
    paths=[parent/'manifest.json',*[parent/n for n in m['libraries']]];rows=[]
    for task in selected:
        folder=parent/task['id'];r=json.loads((folder/'summary.json').read_text());ds=devices[variant]
        if (r['task']!=task or r['error'] is not None or not r['result']['counter_feasibility_passed']
            or (folder/'bench.cir').read_text()!=verification.pilot.fixture(parent,task['spec'],ds)
            or any(sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Require exact complete positive profile cases')
        requested={'v('+n.replace(':','.').lower()+')' for d in ds for n in d['terminals'] if n!='0'}
        validate(folder/'bench.raw',requested,26e-9)
        measured=verification.pilot.measure(folder,task['spec'],ds)
        if measured!=r['result']:raise ValueError('Native profile remeasurement changed')
        rows.append(dict(task=task,result=measured));paths += [folder/n for n in ['summary.json',*r['files']]]
    verification.pilot.bound(parent)
    code=[Path(__file__),Path(verification.__file__),Path(verification.pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),variant=variant,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code})
    out=ROOT/'build/diagnostics/static_phase_profile_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);verification.pilot.atomic(out/'summary.json',dict(identity=identity,rows=rows,
        source_counter_feasibility_passed=True,qualified_phy=False,
        scope='Four independently regenerated and remeasured SS40 cases of one native component-RC counter profile; no other-variant, full-PVT, whole-controller or PHY admission'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--variant',choices=['o1','o2'],required=True)
    a=p.parse_args();print(verify(a.artifact.resolve(),a.variant),flush=True)
