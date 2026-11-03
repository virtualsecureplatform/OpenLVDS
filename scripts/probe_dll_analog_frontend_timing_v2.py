#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Apply the unchanged native timing limits to the revised two-stage frontend.

Only the admitted DC namespace, model policy and producer stamp change.
Fixtures, scoring, stress, ranking and dispatch remain the retained engine.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import probe_dll_analog_frontend_dc_tailtrim as revision
import probe_dll_analog_frontend_timing as original

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_timing_tailtrim'
sha=revision.sha


@contextmanager
def profile():
    previous=original.dc,original.NAMESPACE,original.admission
    admitted=original.admission
    def gate(parent,clock_baseline):
        pm,report,bm=admitted(parent,clock_baseline)
        # Record the profile producer before the unchanged creator hashes its
        # identity. The original DC manifest and its attestation stay untouched.
        pm=deepcopy(pm);pm['identity']['code'][Path(__file__).name]=sha(Path(__file__))
        return pm,report,bm
    proxy=SimpleNamespace(NAMESPACE=revision.NAMESPACE,policy=revision.policy,OUTPUTS=revision.OUTPUTS,
                          verify=revision.verify,bound=revision.bound,screen=revision.screen)
    try:
        original.dc=proxy;original.NAMESPACE=NAMESPACE;original.admission=gate
        yield
    finally:original.dc,original.NAMESPACE,original.admission=previous


def prepare(parent,clock_baseline):
    with profile():return original.prepare(parent,clock_baseline)


def bound(out):
    with profile():return original.bound(out)


def run(out):
    with profile():return original.run(out)


def verify(out):
    with profile():return original.verify(out)


def campaign(parent,clock_baseline):
    out=prepare(parent,clock_baseline)
    print(out,flush=True)
    run(out)
    return verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','bound','run','verify','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--clock-baseline',type=Path)
    a=p.parse_args()
    if a.action in ('prepare','campaign'):
        if not a.clock_baseline:p.error('--clock-baseline required')
        result=globals()[a.action](a.artifact.resolve(),a.clock_baseline.resolve())
    else:result=globals()[a.action](a.artifact.resolve())
    print(result if a.action=='prepare' else json.dumps(result,indent=2),flush=True)
