#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rerun a bounded driver-current correction in unchanged component fixtures."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from driver_current_variant import source_variant, VARIANT
from qualify_driver_restore_components import fixture
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import checked_netlist
from verify_analog import driver_metrics, driver_dc_metrics

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
CASES = ['schematic_driver_sf_40', 'native_driver_sf_40', 'native_driver_ff_0']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_wave(wave):
    if (wave.ndim != 2 or wave.shape[1] != 9 or len(wave) < 2 or
        not np.isfinite(wave).all() or wave[0, 1] > 1e-15 or
        wave[-1, 1] < 2540e-9-1e-12 or np.any(np.diff(wave[:, 1]) <= 0)):
        raise ValueError('Incomplete or invalid original driver waveform')


def measurements(wave):
    complete_wave(wave)
    metrics = driver_metrics(wave)
    metrics['loaded_eye_passed'] = metrics['passed']
    metrics['dc_output'] = driver_dc_metrics(wave)
    metrics['passed'] = metrics['loaded_eye_passed'] and metrics['dc_output']['passed']
    return metrics


def prepare(parent, layout):
    if (engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/driver_components') or
        not layout.is_relative_to(ROOT/'build/diagnostics/driver_layout')):
        raise ValueError('Use completed component evidence and an isolated current-correction layout')
    previous = json.loads((parent/'manifest.json').read_text())
    summary = json.loads((parent/'summary.json').read_text())
    if summary.get('required') != 30 or len(summary.get('results', [])) != 30:
        raise ValueError('Complete all thirty parent cases first')
    physical = json.loads((layout/'summary.json').read_text())
    info = json.loads((layout/'extraction.json').read_text())
    source = source_variant((ROOT/'analog/openlvds.spice').read_text())
    if (not physical['passed'] or physical['identity']['variant'] != VARIANT or
        (layout/'candidate.spice').read_text() != source or
        digest(layout/'candidate.spice') != physical['source_sha256'] or
        info['source_sha256'] != physical['source_sha256']):
        raise ValueError('Physical current-correction source differs from declaration')
    gds = ROOT/physical['designs']['openlvds_driver_core']['gds']
    if digest(gds) != info['gds_sha256']:
        raise ValueError('Current-correction extraction differs from physical GDS')
    audit = audited(layout, info); native = checked_netlist(info)
    inputs = dict(previous['identity']['inputs'])
    paths = [parent/'manifest.json', parent/'summary.json', ROOT/'requirements.json', gds, ROOT/info['netlist'], ROOT/audit['report']]
    paths += [layout/n for n in ['summary.json', 'candidate.spice', 'extraction.json', 'rc_audit.json']]
    paths += [layout/n for n in physical['files']]
    names = set(previous['identity']['code']) | set(physical['identity']['code']) | {
        NAME, 'driver_current_variant.py', 'spice_dispatch.py', 'receiver_static_diagnosis.py'}
    for task in CASES:
        folder = parent/task
        old = json.loads((folder/'summary.json').read_text())
        if (old['manifest_sha256'] != digest(parent/'manifest.json') or
            old['waveform_sha256'] != digest(folder/'bench.cir.prn') or
            old['deck_sha256'] != digest(folder/'bench.cir')):
            raise ValueError('Parent component evidence changed')
        wave, _ = read_wave(folder/'bench.cir.prn')
        expected = measurements(wave)
        if any(old.get(k) != v for k, v in expected.items()):
            raise ValueError('Parent component metrics differ from completed waveform')
        paths += [folder/n for n in ['summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    inputs.update({str(p.relative_to(ROOT)): digest(p) for p in paths})
    for name, stamp in previous['identity']['code'].items():
        if digest(ROOT/'scripts'/name) != stamp:
            raise ValueError('Parent component producer changed')
    if any(digest(ROOT/n) != h for n, h in inputs.items()):
        raise ValueError('Parent component input changed')
    identity = dict(parent=str(parent.relative_to(ROOT)), layout=str(layout.relative_to(ROOT)),
        variant=VARIANT, cases=CASES, inputs=inputs, simulator_provenance=provenance(),
        code={n: digest(ROOT/'scripts'/n) for n in sorted(names)},
        scope='Three diagnostic reruns: matched source/native SF40 and native FF0 upper-swing guard; original fixed supplies, 35 uA reference, 100 ohm/2 pF loads, 2540 ns stimulus and integration policy. Full thirty-case and link qualification remain required.')
    root = ROOT/'build/diagnostics/driver_current'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for task in CASES:
        view = task.split('_')[0]; folder = root/task; folder.mkdir(exist_ok=True)
        body, deck, stop = fixture(parent/task, folder, native if view == 'native' else source, view)
        if abs(stop-2540e-9) > 1e-18:
            raise ValueError('Unexpected original driver stop')
        for name, text in [('source.spice', body), ('bench.cir', deck)]:
            path = folder/name
            if path.exists() and path.read_text() != text:
                raise ValueError('Prepared current-correction fixture changed')
            if not path.exists():
                path.write_text(text)
        tasks.append(dict(id=task, files={n: digest(folder/n) for n in ['source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/driver_current'):
        raise ValueError('Use a prepared diagnostic current-correction campaign')
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']; stamp = digest(root/'manifest.json')
    if [t['id'] for t in manifest['tasks']] != CASES:
        raise ValueError('Incomplete bounded current-correction coverage')
    def unchanged():
        if (digest(root/'manifest.json') != stamp or provenance() != identity['simulator_provenance'] or
            any(digest(ROOT/n) != h for n, h in identity['inputs'].items()) or
            any(digest(ROOT/'scripts'/n) != h for n, h in identity['code'].items()) or
            any(digest(root/t['id']/n) != h for t in manifest['tasks'] for n, h in t['files'].items())):
            raise ValueError('Driver current-correction context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in manifest['tasks']:
            folder = root/task['id']; cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
            if cached is None:
                if any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial driver run retained; prepare a fresh context')
                atomic(root/'state.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=1, label='driver_current_'+task['id']):
                    unchanged(); atomic(root/'state.json', dict(status='running', task=task['id'], qualified_phy=False))
                    process = subprocess.run(command(folder/'ngspice.log', folder/'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr); process.check_returncode()
            elif digest(folder/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Driver current-correction waveform changed')
            wave, _ = read_wave(folder/'bench.cir.prn')
            result = dict(task=task['id'], **measurements(wave), qualified_phy=False,
                manifest_sha256=stamp, waveform_sha256=digest(folder/'bench.cir.prn'), deck_sha256=task['files']['bench.cir'])
            unchanged()
            if cached is not None and cached != result:
                raise ValueError('Driver current-correction metrics differ from waveform')
            capture_manifest(folder/'summary.json', result); results.append(result)
        report = dict(diagnostic_complete=True, qualified_phy=False, results=results,
            passed=all(r['passed'] for r in results), manifest_sha256=stamp, scope=identity['scope'])
        capture_manifest(root/'summary.json', report)
        atomic(root/'state.json', dict(status='completed', passed=report['passed'], qualified_phy=False))
        return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--layout', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.layout is None:
            p.error('--layout is required')
        print(prepare(a.artifact.resolve(), a.layout.resolve()), flush=True)
    else:
        print(json.dumps(run(a.artifact.resolve())), flush=True)
