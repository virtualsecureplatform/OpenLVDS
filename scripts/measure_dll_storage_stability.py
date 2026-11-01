#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run unchanged G/Y and step measurements for the admitted 16 pF native DLL."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import sys

import measure_dll_stability as measurement
import native_ac
import qualify_dll_storage as storage
from receiver_static_diagnosis import capture_manifest
from stability_evidence import PRODUCERS, verified
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
sha = storage.sha


def admitted(qualification, all_pvt=False):
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use the corrected isolated native DLL qualification')
    m = json.loads((qualification/'manifest.json').read_text()); i = m['identity']
    if i.get('variant') != storage.VARIANT:
        raise ValueError('Stability measurement requires the corrected 16 pF DLL variant')
    a = json.loads((qualification/'storage_source_admission.json').read_text())
    if (a.get('variant') != storage.VARIANT or a.get('manifest_sha256') != sha(qualification/'manifest.json') or
            a.get('producer_sha256') != sha(Path(storage.__file__)) or
            any(sha(ROOT/n) != h for n, h in a['proofs'].items())):
        raise ValueError('Storage source admission changed')
    if storage.source_gate(ROOT/i['screen']) != a['proofs']:
        raise ValueError('Storage source remeasurement changed')
    corners = [('ss',0), ('tt',25), ('ff',0)]
    if all_pvt:
        req = json.loads((qualification/'requirements.json').read_text())
        corners = [(p,t) for p in req['process_corners'] for t in req['temperatures_c']]
    needed = {f'loop_{p}_{t}' for p,t in corners}
    needed |= {f'phase_{p}_{t}_{offset}ps' for p,t in corners for offset in [-50,50]}
    needed |= {t['id'] for t in m['tasks'] if storage.native.screen_task(t)}
    tasks = {t['id']:t for t in m['tasks']}
    if (not (qualification/'screen_summary.json').is_file() or
            json.loads((qualification/'screen_summary.json').read_text()).get('passed') is not True or
            not needed <= set(tasks) or any(not (qualification/n/'summary.json').is_file() for n in needed)):
        raise ValueError('Complete the native screen and required operating points before stability measurements')
    # Every selected report already exists, so execute can only remeasure.
    with storage.profile():
        storage.native.validate(qualification,m)
        for name in sorted(needed):
            result = storage.native.execute(qualification,m,tasks[name])
            if result.get('passed') is not True or result['metrics'].get('passed') is not True:
                raise ValueError('Native operating point failed: '+name)
    return m, corners


def context(qualification, manifest, corners, all_pvt=False):
    code = {n: sha(ROOT/'scripts'/n) for n in PRODUCERS}
    identity = dict(code=code, full_inputs=manifest['identity']['full_models']['inputs'],
        library_sha256=sha(qualification/'full.spice'), qualification_manifest_sha256=sha(qualification/'manifest.json'),
        simulator_provenance=measurement.provenance(), corners=corners)
    fingerprint = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    return qualification/('stability_all_pvt' if all_pvt else 'stability_screen')/fingerprint, identity


@contextmanager
def resources():
    previous = measurement.slot, native_ac.slot
    try:
        measurement.slot = lambda: lease(ROOT,priority=1,label='dll_storage_stability_transient')
        native_ac.slot = lambda: lease(ROOT,priority=1,label='dll_storage_stability_ac')
        yield
    finally:
        measurement.slot,native_ac.slot = previous


def run(qualification, all_pvt=False):
    m,corners = admitted(qualification,all_pvt)
    root,identity = context(qualification,m,corners,all_pvt)
    names = tuple(f'{p}_{t}' for p,t in corners)
    with (qualification/'.storage_stability.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if root.exists():
            if not (root/'summary.json').is_file():
                raise ValueError('Partial storage stability output retained; use a fresh context')
            verified(root/'summary.json',m['identity']['full_models']['inputs'],names)
            return root/'summary.json'
        policy = dict(producer_sha256=sha(Path(__file__)),dispatcher_sha256=sha(ROOT/'scripts/spice_dispatch.py'),
            qualification_manifest_sha256=sha(qualification/'manifest.json'),
            scientific_identity=identity,priority=1,global_slot_budget=6,no_outer_lease=True,qualified_phy=False,
            scope='Original G/Y, forced-control delay and both 390/410 MHz step fixtures. Resource/variant adapter only; measured stability does not admit the full native DLL or PHY.')
        ledger = qualification/'storage_stability_scheduling'/hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
        ledger.mkdir(parents=True,exist_ok=True);capture_manifest(ledger/'manifest.json',policy)
        previous = sys.argv
        try:
            sys.argv = [str(Path(measurement.__file__)),str(qualification)]+(['--all-pvt'] if all_pvt else [])
            with storage.profile(),resources():
                measurement.main()
        finally:
            sys.argv = previous
        if json.loads((root/'manifest.json').read_text()) != json.loads(json.dumps(identity)):
            raise ValueError('Storage stability scientific identity differs from its original producer')
        verified(root/'summary.json',m['identity']['full_models']['inputs'],names)
        return root/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path)
    p.add_argument('--all-pvt',action='store_true');a=p.parse_args()
    print(run(a.qualification.resolve(),a.all_pvt),flush=True)
