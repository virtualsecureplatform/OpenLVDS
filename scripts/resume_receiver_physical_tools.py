#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recover the pre-geometry missing-NumPy handoff using the container Python."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import continue_receiver_soft_common_mode_physical as controller
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
sha=controller.sha


def invocation(args):
    expected=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3']
    if isinstance(args,(list,tuple)) and list(args[:4])==expected:
        return list(args[:3])+['/usr/bin/python3']+list(args[4:])
    return args


@contextmanager
def python_profile():
    previous=controller.subprocess.run
    try:
        controller.subprocess.run=lambda args,**kwargs:previous(invocation(args),**kwargs)
        yield
    finally:
        controller.subprocess.run=previous


def prepare(prior):
    if not prior.is_relative_to(ROOT/'build/diagnostics/receiver_physical_followup'):
        raise ValueError('Use the failed isolated physical handoff')
    m=json.loads((prior/'manifest.json').read_text());state=json.loads((prior/'state.json').read_text())
    log=prior/'rail_pullup_2r_layout.log'
    if (state.get('status')!='held_for_diagnosis' or not log.is_file() or
            "ModuleNotFoundError: No module named 'numpy'" not in log.read_text() or
            any((prior/(v+'_prepared.json')).exists() or (prior/(v+'_result.json')).exists() for v in controller.VARIANTS)):
        raise ValueError('Recovery requires the specific pre-geometry missing-NumPy failure')
    if any(sha(ROOT/n)!=h for n,h in m['files'].items()):
        raise ValueError('Original failed handoff inputs changed')
    matrix=ROOT/m['matrix'];followup=matrix/'clock_followup'
    if not (followup/'summary.json').is_file():
        raise ValueError('Complete source-clock admission before tool-only recovery')
    report=json.loads((followup/'summary.json').read_text())
    if report.get('manifest_sha256')!=sha(followup/'manifest.json'):
        raise ValueError('Completed source-clock followup changed')
    paths=[prior/'manifest.json',prior/'state.json',log,Path(__file__),followup/'summary.json']
    for variant in controller.VARIANTS:
        receipt=followup/(variant+'_result.json');r=json.loads(receipt.read_text())
        if controller.admitted_clock(matrix,variant,r) is None:
            raise ValueError('Both exact weaker source-clock admissions are required')
        paths.append(receipt)
    identity=dict(m,resume_from=str(prior.relative_to(ROOT)),tool_python='/usr/bin/python3',
        recovery_scope='Interpreter selection only. Original failed controller, scientific source/fixtures, passed source gates and all physical/native requirements remain unchanged.',
        files=dict(m['files'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}))
    out=ROOT/'build/diagnostics/receiver_physical_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',identity)
    return out


def run(out):
    m=json.loads((out/'manifest.json').read_text())
    if m.get('tool_python')!='/usr/bin/python3' or m['files'].get(str(Path(__file__).relative_to(ROOT)))!=sha(Path(__file__)):
        raise ValueError('Recovery policy or interpreter adapter changed')
    with python_profile():
        return controller.run(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':
        print(prepare(a.artifact.resolve()),flush=True)
    else:
        run(a.artifact.resolve())
