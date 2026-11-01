#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe native driver stages in a completed link fixture without circuit changes."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic, text_block
from dll_measurements import read_wave
from reduce_rc import number
from simulate_link import edge_times, REQ
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT = Path(__file__).resolve().parents[1]
CODE = ['probe_driver_internal.py', 'dll_campaign.py', 'dll_measurements.py', 'reduce_rc.py',
        'simulate_link.py', 'spice_engine.py', 'spice_probes.py', 'spice_slots.py', 'run_ngspice.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aliases(library):
    driver = text_block(library, 'openlvds_driver_core')
    nodes = {}
    for leaf in ['XLS__AD', 'XLS__AB', 'XLS__L', 'XLS__R', 'DP', 'DN']:
        base = 'openlvds_driver_core__' + leaf
        found = sorted(set(re.findall(r'\b' + base + r'(?:\.t\d+)?\b', driver)))
        if base not in found:
            raise ValueError('Missing named driver observation bus: ' + leaf)
        nodes[leaf] = base
    return {lane + '_' + leaf: instance + ':' + node
            for lane, instance in [('clock', 'XCT'), ('data', 'XDT')] for leaf, node in nodes.items()}


def instrument(deck, parent, root, probes):
    old = f'.include "{parent}/library.spice"'
    if deck.count(old) != 1:
        raise ValueError('Expected one parent library binding')
    deck = deck.replace(old, f'.include "{root}/library.spice"')
    rows = list(re.finditer(r'(?im)^\.print tran[^\n]*', deck))
    if len(rows) != 1:
        raise ValueError('Expected one parent voltage observation row')
    end = rows[0].end()
    return deck[:end] + ' ' + ' '.join('V(' + node + ')' for node in probes.values()) + deck[end:]


def prepare(parent):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT / 'build/diagnostics/receiver_candidate_link'):
        raise ValueError('Use a completed native receiver link diagnostic in the pinned runtime')
    capture = json.loads((parent / 'manifest.json').read_text())
    identity = capture['identity']
    summary = json.loads((parent / 'summary.json').read_text())
    for name, stamp in identity['inputs'].items():
        if digest(ROOT / name) != stamp:
            raise ValueError('Parent link input changed')
    for name, stamp in identity['code'].items():
        if digest(ROOT / 'scripts' / name) != stamp:
            raise ValueError('Parent link producer changed')
    if provenance() != identity['simulator_provenance']:
        raise ValueError('Parent link runtime changed')
    for name, stamp in [('manifest.json', summary['manifest_sha256']), ('bench.cir', summary['deck_sha256']),
                        ('bench.cir.prn', summary['waveform_sha256']), ('library.spice', capture['library_sha256'])]:
        if digest(parent / name) != stamp:
            raise ValueError('Parent link evidence changed')
    library = (parent / 'library.spice').read_text()
    probes = aliases(library)
    deck = (parent / 'bench.cir').read_text()
    tran = re.search(r'(?im)^\.tran\s+\S+\s+(\S+)', deck)
    if not tran or number(tran[1]) < 120e-9:
        raise ValueError('Original transient does not cover the diagnostic interval')
    files = [parent / n for n in ['manifest.json', 'summary.json', 'bench.cir', 'library.spice', 'bench.cir.prn']]
    selected = dict(parent=str(parent.relative_to(ROOT)), observation_nodes=probes, stop_seconds=number(tran[1]),
        simulator_provenance=provenance(), interval_ns=[60, 120],
        inputs={str(p.relative_to(ROOT)): digest(p) for p in files},
        code={n: digest(ROOT / 'scripts' / n) for n in sorted(set(CODE) | set(identity['code']))})
    root = ROOT / 'build/diagnostics/driver_internal' / hashlib.sha256(
        json.dumps(selected, sort_keys=True).encode()).hexdigest()[:16]
    if (root / 'manifest.json').exists():
        return root
    root.mkdir(parents=True)
    modified = instrument(deck, parent, root, probes)
    ProbeNetwork(library).validate(modified, probes.values())
    (root / 'library.spice').write_text(library)
    (root / 'bench.cir').write_text(modified)
    atomic(root / 'manifest.json', dict(identity=selected, qualified_phy=False,
           files={n: digest(root / n) for n in ['bench.cir', 'library.spice']}))
    return root


def run(root):
    if not root.is_relative_to(ROOT / 'build/diagnostics/driver_internal'):
        raise ValueError('Use an isolated native driver observation fixture')
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = manifest['identity']
    parent = ROOT / identity['parent']

    def unchanged():
        if provenance() != identity['simulator_provenance']:
            raise ValueError('Driver observation runtime changed')
        for name, stamp in identity['inputs'].items():
            if digest(ROOT / name) != stamp:
                raise ValueError('Driver observation parent changed')
        for name, stamp in identity['code'].items():
            if digest(ROOT / 'scripts' / name) != stamp:
                raise ValueError('Driver observation producer changed')
        if any(digest(root / name) != stamp for name, stamp in manifest['files'].items()):
            raise ValueError('Driver observation fixture changed')
        if ((root / 'library.spice').read_bytes() != (parent / 'library.spice').read_bytes() or
                (root / 'bench.cir').read_text() != instrument((parent / 'bench.cir').read_text(),
                    parent, root, identity['observation_nodes'])):
            raise ValueError('Driver observation changes more than voltage probes')

    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        cached = json.loads((root / 'summary.json').read_text()) if (root / 'summary.json').exists() else None
        if cached is None:
            atomic(root / 'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with slot():
                unchanged()
                atomic(root / 'execution.json', dict(status='running', qualified_phy=False))
                process = subprocess.run(command(root / 'ngspice.log', root / 'bench.cir'),
                                         cwd=root, capture_output=True, text=True)
            (root / 'console.log').write_text(process.stdout + process.stderr)
            process.check_returncode()
        unchanged()
        wave, headers = read_wave(root / 'bench.cir.prn')
        t = wave[:, 1]
        if not np.isfinite(wave).all() or np.any(np.diff(t) <= 0) or t[-1] < identity['stop_seconds'] - 1e-12:
            raise ValueError('Incomplete or invalid driver observation transient')
        original, original_headers = read_wave(parent / 'bench.cir.prn')
        grid = np.linspace(60e-9, 120e-9, 5001)
        comparison = {name: float(np.max(abs(np.interp(grid, t, wave[:, headers[name]]) -
                      np.interp(grid, original[:, 1], original[:, original_headers[name]]))))
                      for name in ['V(TXCLOCK)', 'V(CP)', 'V(CN)', 'V(RCP)', 'V(RCN)']}
        keep = (t >= 60e-9) & (t <= 120e-9)
        observed = {}
        for label, node in identity['observation_nodes'].items():
            values = wave[:, headers['V(' + node.upper() + ')']]
            level = .9 if label.endswith(('__AD', '__AB')) else 1.65
            events = {}
            for name, rising in [('rising', True), ('falling', False)]:
                crossings = edge_times(t, values, level, rising)
                events[name + '_ns'] = (crossings[(crossings >= 60e-9) & (crossings <= 120e-9)] * 1e9).tolist()
            observed[label] = dict(min_v=float(values[keep].min()), max_v=float(values[keep].max()),
                                   crossing_level_v=level, **events)
        eyes = {}
        for name, p, n in [('tx_clock', 'CP', 'CN'), ('rx_clock', 'RCP', 'RCN')]:
            difference = wave[:, headers['V(' + p + ')']] - wave[:, headers['V(' + n + ')']]
            crossings = edge_times(t, difference, 0)
            centers = (crossings[:-1] + crossings[1:]) / 2
            centers = centers[(centers >= 60e-9) & (centers <= 120e-9)]
            amplitudes = abs(np.interp(centers, t, difference))
            if not len(centers):
                raise ValueError('No complete clock pulse centers')
            eyes[name] = dict(min_center_abs_v=float(amplitudes.min()),
                centers_below_rx_threshold=int(np.count_nonzero(amplitudes < REQ['rx_threshold_v'])),
                centers_ns=(centers * 1e9).tolist(), center_abs_v=amplitudes.tolist())
        result = dict(diagnostic_complete=True, qualified_phy=False, observation_nodes=observed, clock_centers=eyes,
            original_trace_comparison_max_abs_v=comparison,
            manifest_sha256=digest(root / 'manifest.json'), waveform_sha256=digest(root / 'bench.cir.prn'),
            scope='Original native link circuit and full transient with added unloaded voltage probes; no PHY qualification')
        if cached is not None and cached != result:
            raise ValueError('Driver observation cached analysis differs from waveform')
        atomic(root / 'summary.json', result)
        atomic(root / 'execution.json', dict(status='completed', qualified_phy=False))
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
