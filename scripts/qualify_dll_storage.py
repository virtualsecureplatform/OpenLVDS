#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Admit the 16 pF storage correction to the original native DLL qualification."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path

import qualify_dll_candidate as native
import screen_dll_storage as source
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
VARIANT = source.VARIANT
sha = source.reference.digest


def source_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/dll_architecture'):
        raise ValueError('Use the prepared 16 pF source-acquisition screen')
    m = json.loads((screen/'manifest.json').read_text()); source.validate(screen, m)
    if not (screen/'summary.json').is_file() or any(not (screen/t['id']/'summary.json').is_file() for t in m['tasks']):
        raise ValueError('Complete all three 16 pF source-acquisition cases before native qualification')
    if (json.loads((screen/'summary.json').read_text()).get('passed') is not True or
            any(json.loads((screen/t['id']/'summary.json').read_text()).get('passed') is not True for t in m['tasks'])):
        raise ValueError('Every original 16 pF source-acquisition case must pass')
    with (screen/'.native_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with (screen/'.execution.lock').open('a+') as producer:
            fcntl.flock(producer, fcntl.LOCK_EX)
        if source.run(screen, 1) != 0:
            raise ValueError('Remeasured 16 pF source acquisition failed')
    paths = [screen/n for n in ['manifest.json', 'summary.json', 'inputs/'+VARIANT+'.spice']]
    for t in m['tasks']:
        paths.extend(screen/t['id']/n for n in ['summary.json', 'bench.cir.prn', 'bench.cir', 'library.spice'])
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


@contextmanager
def profile():
    previous = native.CODE, native.slot
    try:
        native.CODE = sorted(set(native.CODE) | {NAME, 'screen_dll_storage.py', 'preset_dll_experiment.py',
            'dll_storage_compensation.py', 'spice_dispatch.py', 'receiver_static_diagnosis.py'})
        native.slot = lambda: lease(ROOT, priority=1, label='native_dll_storage16')
        yield
    finally:
        native.CODE, native.slot = previous


def prepare(layout, pfd, screen):
    proofs = source_gate(screen)
    if (layout/'candidate.spice').read_bytes() != (screen/'inputs'/(VARIANT+'.spice')).read_bytes():
        raise ValueError('Native DLL physical source differs from the admitted 16 pF circuit')
    with profile():
        out = native.prepare(layout, pfd, screen, VARIANT)
    capture_manifest(out/'storage_source_admission.json', dict(variant=VARIANT, proofs=proofs,
        manifest_sha256=sha(out/'manifest.json'), producer_sha256=sha(Path(__file__)), qualified_phy=False,
        scope='Completed original SS0/TT25/FF0 source acquisition only. Native screen, measured stability, full 336-case qualification and PHY admission remain required.'))
    return out


def run(out, jobs=2, stage='screen', stability=None):
    if not out.is_relative_to(ROOT/'build/diagnostics/dll_qualification') or jobs not in [1, 2, 3]:
        raise ValueError('Use an isolated storage DLL qualification with one to three workers')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    admission = json.loads((out/'storage_source_admission.json').read_text())
    if (i.get('variant') != VARIANT or admission.get('variant') != VARIANT or
            admission.get('manifest_sha256') != sha(out/'manifest.json') or
            admission.get('producer_sha256') != sha(Path(__file__)) or
            any(sha(ROOT/n) != h for n, h in admission['proofs'].items())):
        raise ValueError('Storage DLL source admission changed')
    if source_gate(ROOT/i['screen']) != admission['proofs']:
        raise ValueError('Storage DLL source remeasurement changed')
    # The old engine permits partial-file retries. This adapter preserves them
    # instead, before any existing worker can overwrite a numerical failure.
    for t in m['tasks']:
        folder = out/t['id']
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
            raise ValueError('Partial 16 pF native output retained; use a fresh context')
    with profile():
        return native.run(out, jobs, stage, stability)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('layout', type=Path); a.add_argument('pfd', type=Path); a.add_argument('screen', type=Path)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path); a.add_argument('--jobs', type=int, choices=[1, 2, 3], default=2)
    a.add_argument('--stage', choices=['screen', 'full'], default='screen'); a.add_argument('--stability', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.layout.resolve(), a.pfd.resolve(), a.screen.resolve()), flush=True)
    else:
        raise SystemExit(run(a.artifact.resolve(), a.jobs, a.stage, a.stability.resolve() if a.stability else None))
