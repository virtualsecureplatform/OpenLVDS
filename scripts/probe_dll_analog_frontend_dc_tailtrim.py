#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure a geometric mirror correction after the complete fingered DC grid."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
from pathlib import Path

import dll_analog_frontend_v2_tailtrim as policy
import probe_dll_analog_frontend_dc_v2_fingered as original

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_dc_tailtrim'
PARENT_NAMESPACE='dll_analog_frontend_dc_v2_fingered'
sha=original.sha
OUTPUTS=original.OUTPUTS
screen=original.screen


def parent_context(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics'/PARENT_NAMESPACE):raise ValueError('Require the complete fingered DC revision')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);report=original.verify(parent);m=original.bound(parent)
    if report['dc_ready_variants']:raise ValueError('Use the failed complete mirror-current grid as the correction prerequisite')
    for r in report['results']:
        q=r['result']
        if (not q['parallel_devices_passed'] or not q['common_mode_passed'] or not q['reference_matching_passed'] or
            any(not p['passed'] for p in q['references'].values()) or any(not s['passed'] for s in q['stress']) or
            any(not o['passed'] for o in q['outputs'].values()) or any(not q['tails'][n]['passed'] for n in ('ref_dec','fb_dec')) or
            any(q['tails'][n]['headroom_v']<.02 for n in ('ref_pre','fb_pre'))):
            raise ValueError('Mirror-current correction cannot hide an unrelated DC failure')
    return m


@contextmanager
def profile(extra_inputs=None):
    # Stamp the correction before the retained creator hashes its identity.
    previous=original.policy,original.NAMESPACE,original.original.failed_context
    admitted=original.original.failed_context
    def gate(parent):
        pm=deepcopy(admitted(parent))
        for name in (Path(__file__).name,'dll_analog_frontend_v2_tailtrim.py'):
            pm['identity']['code'][name]=sha(ROOT/'scripts'/name)
        pm['identity']['inputs'].update(extra_inputs or {})
        return pm
    try:
        original.policy=policy;original.NAMESPACE=NAMESPACE;original.original.failed_context=gate
        yield
    finally:original.policy,original.NAMESPACE,original.original.failed_context=previous


def prepare(parent,invalid):
    m=parent_context(parent)
    paths=[p for p in parent.rglob('*') if p.is_file()]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
    with profile(inputs):return original.prepare(ROOT/m['identity']['failed_revision'],invalid)


def parent_from_inputs(out):
    if not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE):raise ValueError('Require the mirror-corrected DC artifact')
    m=json.loads((out/'manifest.json').read_text())
    parents=[Path(n).parent for n in m['identity']['inputs'] if Path(n).name=='manifest.json' and Path(n).parent.parent==Path('build/diagnostics')/PARENT_NAMESPACE]
    if len(parents)!=1:raise ValueError('Require exactly one captured fingered-grid prerequisite')
    return ROOT/parents[0]


def bound(out):
    parent_context(parent_from_inputs(out))
    with profile():return original.bound(out)


def run(out):
    parent_context(parent_from_inputs(out))
    with profile():return original.run(out)


def verify(out):
    parent_context(parent_from_inputs(out))
    with profile():return original.verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','bound','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--invalid',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.invalid:p.error('--invalid required')
        result=prepare(a.artifact.resolve(),a.invalid.resolve())
    else:result=globals()[a.action](a.artifact.resolve())
    print(result if a.action=='prepare' else json.dumps(result,indent=2),flush=True)
