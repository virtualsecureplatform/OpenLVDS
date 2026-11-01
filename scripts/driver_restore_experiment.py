#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare source driver restoration ratios in the unchanged saved native link."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from driver_restore_variant import source_variant, TOP
from dll_campaign import atomic
from dll_measurements import read_wave
from probe_driver_internal import instrument as observation_instrument
from reduce_rc import number
from simulate_link import analyze, edge_times, word_stream, REQ
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash
from spice_slots import slot
from stage_phy_candidate import overlay

ROOT = Path(__file__).resolve().parents[1]
CODE = ['driver_restore_experiment.py', 'driver_restore_variant.py', 'dll_campaign.py', 'dll_measurements.py',
        'probe_driver_internal.py', 'reduce_rc.py', 'simulate_link.py', 'spice_engine.py', 'spice_probes.py',
        'spice_scope.py', 'spice_slots.py', 'stage_phy_candidate.py', 'run_ngspice.py', 'layout.py']
PROTECTED = ('openlvds_receiver_core', 'lvds_bias', 'openlvds_dll', 'openlvds_delay_line',
             'openlvds_tx_core', 'openlvds_ddr_rx')
CASES = ['source_control', 'restore_64_24']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(parent_deck, parent, folder):
    deck = observation_instrument(parent_deck, parent, folder, {})
    # Only source-model node names differ from the native driver's named buses.
    deck = re.sub(r'(?i)(V\(X(?:CT|DT):)openlvds_driver_core__', r'\1', deck)
    probes = {lane + '_' + node: instance + ':' + node
              for lane, instance in [('clock', 'XCT'), ('data', 'XDT')] for node in ['DP', 'DN']}
    match = re.search(r'(?im)^\.print tran[^\n]*', deck)
    return deck[:match.end()] + ' '.join('V(' + n + ')' for n in probes.values()) + deck[match.end():], probes


def prepare(parent):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT / 'build/diagnostics/receiver_candidate_link'):
        raise ValueError('Use the completed saved native receiver link')
    capture = json.loads((parent / 'manifest.json').read_text())
    context = capture['identity']
    report = json.loads((parent / 'summary.json').read_text())
    for name, stamp in context['inputs'].items():
        if digest(ROOT / name) != stamp:
            raise ValueError('Parent link input changed')
    for name, stamp in context['code'].items():
        if digest(ROOT / 'scripts' / name) != stamp:
            raise ValueError('Parent link producer changed')
    if provenance() != context['simulator_provenance']:
        raise ValueError('Parent link runtime changed')
    for name, stamp in [('manifest.json', report['manifest_sha256']), ('bench.cir', report['deck_sha256']),
                        ('bench.cir.prn', report['waveform_sha256']), ('library.spice', capture['library_sha256'])]:
        if digest(parent / name) != stamp:
            raise ValueError('Parent link evidence changed')
    paths = [parent / n for n in ['manifest.json', 'summary.json', 'bench.cir', 'bench.cir.prn', 'library.spice']]
    paths += [ROOT / 'analog/openlvds.spice', ROOT / 'requirements.json']
    identity = dict(parent=str(parent.relative_to(ROOT)), parent_config=context['parent_config'],
        simulator_provenance=provenance(), source_driver_only=True, parallel_jobs=2,
        inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
        code={n: digest(ROOT / 'scripts' / n) for n in sorted(set(CODE) | set(context['code']))})
    root = ROOT / 'build/diagnostics/driver_restore' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if (root / 'manifest.json').exists():
        return root
    root.mkdir(parents=True)
    baseline = (parent / 'library.spice').read_text()
    source = (ROOT / 'analog/openlvds.spice').read_text()
    tasks = []
    parent_deck = (parent / 'bench.cir').read_text()
    stop = re.search(r'(?im)^\.tran\s+\S+\s+(\S+)', parent_deck)
    if not stop:
        raise ValueError('Missing original transient endpoint')
    for name in CASES:
        folder = root / name
        folder.mkdir()
        selected = source_variant(source, name == 'restore_64_24')
        library = overlay(baseline, selected, TOP, PROTECTED)
        if closure_hash(library, TOP) != closure_hash(selected, TOP):
            raise ValueError('Selected source driver differs from its declared variant')
        deck, probes = fixture(parent_deck, parent, folder)
        # Validate both added observations and renamed native driver nodesets.
        internal = re.findall(r'(?i)V\((X(?:CT|DT):[^)]+)\)', deck)
        ProbeNetwork(library).validate(deck, internal)
        (folder / 'library.spice').write_text(library)
        (folder / 'bench.cir').write_text(deck)
        tasks.append(dict(id=name, source_driver_only=True, stop_seconds=number(stop[1]), observation_nodes=probes,
            files={n: digest(folder / n) for n in ['library.spice', 'bench.cir']}))
    atomic(root / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT / 'build/diagnostics/driver_restore'):
        raise ValueError('Use a prepared source driver restoration experiment')
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = manifest['identity']
    if identity['parallel_jobs'] != 2 or [t['id'] for t in manifest['tasks']] != CASES:
        raise ValueError('Both source driver controls are required exactly once')

    def unchanged():
        if provenance() != identity['simulator_provenance']:
            raise ValueError('Driver restoration runtime changed')
        for name, stamp in identity['inputs'].items():
            if digest(ROOT / name) != stamp:
                raise ValueError('Driver restoration input changed')
        for name, stamp in identity['code'].items():
            if digest(ROOT / 'scripts' / name) != stamp:
                raise ValueError('Driver restoration producer changed')
        parent = ROOT / identity['parent']
        baseline = (parent / 'library.spice').read_text()
        source = (ROOT / 'analog/openlvds.spice').read_text()
        for task in manifest['tasks']:
            folder = root / task['id']
            if any(digest(folder / n) != h for n, h in task['files'].items()):
                raise ValueError('Driver restoration fixture changed')
            expected = overlay(baseline, source_variant(source, task['id'] == 'restore_64_24'), TOP, PROTECTED)
            deck, _ = fixture((parent / 'bench.cir').read_text(), parent, folder)
            if (folder / 'library.spice').read_text() != expected or (folder / 'bench.cir').read_text() != deck:
                raise ValueError('Driver restoration changes more than the declared source driver')

    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        def execute(task):
            folder = root / task['id']
            cached = json.loads((folder / 'summary.json').read_text()) if (folder / 'summary.json').exists() else None
            if cached is None:
                atomic(folder / 'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
                with slot():
                    unchanged()
                    atomic(folder / 'execution.json', dict(status='running', qualified_phy=False))
                    process = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                             cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(process.stdout + process.stderr)
                process.check_returncode()
            unchanged()
            wave, headers = read_wave(folder / 'bench.cir.prn')
            t = wave[:, 1]
            if not np.isfinite(wave).all() or np.any(np.diff(t) <= 0) or t[-1] < task['stop_seconds'] - 1e-12:
                raise ValueError('Incomplete driver restoration trace')
            config = identity['parent_config']
            rises = edge_times(t, wave[:, headers['V(CLK0)']], .9, True)
            launch = rises[rises >= config['training_ns'] * 1e-9][:config['bits'] // 2] * 1e9
            if len(launch) != config['bits'] // 2:
                raise ValueError('Incomplete original payload launch sequence')
            decoded = analyze(wave, word_stream(len(launch)), launch, 1000 / config['mhz'])
            decoded['sampling_margin_passed'] = all(decoded.get(k) is not None and
                decoded[k] >= REQ['minimum_sampling_margin_ps'] for k in ['setup_margin_ps', 'hold_margin_ps'])
            decoded['passed'] = decoded['passed'] and decoded['sampling_margin_passed']
            eyes = {}
            for lane, p, n in [('tx_clock', 'CP', 'CN'), ('rx_clock', 'RCP', 'RCN')]:
                values = wave[:, headers['V(' + p + ')']] - wave[:, headers['V(' + n + ')']]
                crossings = edge_times(t, values, 0)
                centers = (crossings[:-1] + crossings[1:]) / 2
                centers = centers[(centers >= 60e-9) & (centers <= 120e-9)]
                magnitude = abs(np.interp(centers, t, values))
                if not len(magnitude):
                    raise ValueError('No complete clock pulse centers')
                eyes[lane] = dict(min_center_abs_v=float(magnitude.min()),
                    below_rx_threshold=int(np.count_nonzero(magnitude < REQ['rx_threshold_v'])))
            result = dict(task=task['id'], diagnostic_complete=True, qualified_phy=False, source_driver_only=True,
                decoder=decoded, clock_centers=eyes, manifest_sha256=digest(root / 'manifest.json'),
                waveform_sha256=digest(folder / 'bench.cir.prn'),
                scope='Matched schematic driver variants in the unchanged native link fixture; no native driver or PHY qualification')
            if cached is not None and cached != result:
                raise ValueError('Driver restoration cached analysis differs from waveform')
            atomic(folder / 'summary.json', result)
            atomic(folder / 'execution.json', dict(status='completed', qualified_phy=False))
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, manifest['tasks']))
        unchanged()
        atomic(root / 'summary.json', dict(diagnostic_complete=True, qualified_phy=False,
            source_driver_only=True, manifest_sha256=digest(root / 'manifest.json'), results=results))
    print(root / 'summary.json', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
