#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay corrected native-driver pin voltages through the same frontend-local RX."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import driver_current_native as driver
import probe_receiver_frontend as frontend
from diagnose_link_clock import pulse_transport
from dll_campaign import atomic
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
PINS = ['RP', 'RN', 'RCP', 'RCN']
SCOPE = ('Same audited frontend-local native receiver, bias and digital RX load, '
         'with corrected native P64/N24 110:1 driver pin voltages from a completed '
         'loaded diagnostic. Original 50–120 ns interval is shifted to 5–75 ns; '
         'every original PWL knot is retained. Ideal pin sources suppress loading '
         'feedback; short training and original receiver-screen failures remain '
         'separate. This diagnostic does not provide source/native/PHY admission.')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded(wave, headers):
    t = wave[:, 1]
    if (not np.isfinite(wave).all() or t[0] > 50e-9 or t[-1] < 120e-9 or
            np.any(np.diff(t) <= 0)):
        raise ValueError('Complete the driver trace over the full recorded interval')
    # Reuse a recorded endpoint within floating-point roundoff. Adding a
    # second ideal-source breakpoint a few ulps away creates an artificial
    # sub-femtosecond interval despite identical intended timestamps.
    start, end = 50e-9, 120e-9
    left, right = 8*np.spacing(start), 8*np.spacing(end)
    knots = t[(t >= start-left) & (t <= end+right)].copy()
    retained = len(knots)
    if not len(knots) or knots[0] > start+left:
        knots = np.concatenate(([start], knots))
    if knots[-1] < end-right:
        knots = np.concatenate((knots, [end]))
    times = knots-45e-9
    rows = {}; ranges = {}
    for n in PINS:
        values = np.interp(knots, t, wave[:, headers['V('+n+')']])
        rows[n] = 'V'+n+' '+n+' 0 PWL(0 '+f'{values[0]:.17g} '+' '.join(
            f'{at:.17g} {v:.17g}' for at, v in zip(times, values))+')'
        ranges[n] = dict(min_v=float(values.min()), max_v=float(values.max()))
    return rows, dict(original_interval_ns=[50, 120], replay_interval_ns=[5, 75],
        retained_original_knots=retained, total_replay_knots=len(knots), resampling=False,
        endpoint_roundoff_tolerance_s=float(max(left, right)), pin_ranges_v=ranges,
        voltage_window_passed=all(v['min_v'] >= 0 and v['max_v'] <= 2.4 for v in ranges.values()))


def fixture(deck, old, new, rows):
    include = f'.include "{old}/library.spice"'
    if deck.count(include) != 1 or '.tran 5p 80n 0 1p' not in deck:
        raise ValueError('Require the complete original 80 ns/1 ps native fixture')
    deck = deck.replace(include, f'.include "{new}/library.spice"')
    for n in PINS:
        deck, count = re.subn(r'(?m)^V'+n+' '+n+r' 0 PWL\([^\n]*\)$', lambda _: rows[n], deck)
        if count != 1:
            raise ValueError('Expected one original recorded pin source '+n)
    return deck


def prepare(receiver, comparison):
    if (engine() != 'ngspice' or not receiver.is_relative_to(ROOT/'build/diagnostics/receiver_replay') or
            not comparison.is_relative_to(ROOT/'build/diagnostics/driver_native_restore')):
        raise ValueError('Use completed frontend-local receiver and corrected-driver diagnostics')
    for p in [receiver/'summary.json', receiver/'captured/summary.json', receiver/'sharp_control/summary.json',
              comparison/'summary.json', comparison/'restore_64_24/summary.json', comparison/'source_control/summary.json']:
        if not p.is_file():
            raise ValueError('Complete both receiver controls and both driver comparisons first')
    # Cached scientific verification may not dispatch missing original cases.
    frontend.run(receiver); driver.run(comparison)
    rm = json.loads((receiver/'manifest.json').read_text()); dm = json.loads((comparison/'manifest.json').read_text())
    selected = comparison/'restore_64_24'; wave, headers = read_wave(selected/'bench.cir.prn')
    pins, certificate = recorded(wave, headers)
    config = dm['identity']['parent_config']
    original = (receiver/'captured/bench.cir').read_text()
    if (config['process'] != 'ss' or config['temperature'] != 40 or config['mhz'] != 410 or
            not re.search(r'(?m)^\.lib .* ss$', original) or '.options device temp=40\n' not in original):
        raise ValueError('Require matched SS40/410 MHz diagnostics')
    paths = [receiver/n for n in ['manifest.json', 'summary.json', 'library.spice',
        'captured/summary.json', 'captured/bench.cir', 'captured/bench.cir.prn', 'sharp_control/summary.json']]
    paths.extend(comparison/n for n in ['manifest.json', 'summary.json'])
    paths.extend(selected/n for n in ['bench.cir', 'library.spice', 'summary.json', 'bench.cir.prn'])
    names = set(rm['identity']['code']) | set(dm['identity']['code']) | {
        NAME, 'probe_receiver_frontend.py', 'driver_current_native.py', 'spice_dispatch.py'}
    identity = dict(receiver=str(receiver.relative_to(ROOT)), driver=str(comparison.relative_to(ROOT)),
        scope=SCOPE, simulator_provenance=provenance(), maximum_step_ps=1, stop_ns=80,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)})
    root = ROOT/'build/diagnostics/receiver_current_pins'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    for n, text in [('library.spice', (receiver/'library.spice').read_text()),
                    ('bench.cir', fixture(original, receiver, root, pins))]:
        p = root/n
        if p.exists() and p.read_text() != text:
            raise ValueError('Prepared corrected-driver pin fixture changed')
        if not p.exists():
            p.write_text(text)
    capture_manifest(root/'manifest.json', dict(identity=identity, recorded_inputs=certificate, qualified_phy=False,
        files={n: sha(root/n) for n in ['library.spice', 'bench.cir']}))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_current_pins'):
        raise ValueError('Use a prepared corrected-driver native receiver replay')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/n) != h for n, h in m['files'].items())):
            raise ValueError('Corrected-driver native receiver context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((root/'summary.json').read_text()) if (root/'summary.json').exists() else None
        if cached is None:
            if any((root/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                raise ValueError('Partial current-pin receiver replay retained; use a fresh context')
            atomic(root/'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with lease(ROOT, priority=1, label='native-rx-corrected-driver-pins'):
                unchanged(); atomic(root/'execution.json', dict(status='running', qualified_phy=False))
                p = subprocess.run(command(root/'ngspice.log', root/'bench.cir'), cwd=root, capture_output=True, text=True)
            (root/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
        elif sha(root/'bench.cir.prn') != cached['waveform_sha256']:
            raise ValueError('Completed current-pin receiver waveform changed')
        unchanged(); w, h = read_wave(root/'bench.cir.prn'); t = w[:, 1]
        if t[0] > 1e-15 or t[-1] < 80e-9-1e-12:
            raise ValueError('Incomplete full 80 ns receiver replay')
        col = lambda n: w[:, h['V('+n.upper()+')']]
        transport = pulse_transport(t, col('RCP')-col('RCN'), col('RXCLOCK'), 15e-9, 75e-9)
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp,
            waveform_sha256=sha(root/'bench.cir.prn'), receiver_transport=transport,
            diagnostic_clock_passed=bool(len(transport['pulses']) == 47 and
                all(p['output_edges_in_next_input_period'] == 1 for p in transport['pulses'])), scope=SCOPE)
        unchanged()
        if cached is not None and cached != report:
            raise ValueError('Corrected-driver receiver remeasurement changed')
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False,
            missing_output_edges=transport['missing_output_edges']))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); s = p.add_subparsers(dest='action', required=True)
    a = s.add_parser('prepare'); a.add_argument('receiver', type=Path); a.add_argument('driver', type=Path)
    a = s.add_parser('run'); a.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.receiver.resolve(), a.driver.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
