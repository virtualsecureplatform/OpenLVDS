#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate native digital RX using every recorded restored-data/clock PWL knot."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import selected_analog_pilot as pilot
from dll_campaign import atomic, closure
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from reduce_rc import number
from simulate_link import edge_times
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_ddr_rx'
NAMES = ['RXDATA', 'RXCLOCK', 'Q0', 'Q1', 'RXVALID']
CODE = [Path(__file__).name, 'dll_campaign.py', 'dll_measurements.py',
        'receiver_static_diagnosis.py', 'reduce_rc.py', 'simulate_link.py',
        'spice_dispatch.py', 'spice_slots.py', 'spice_engine.py',
        'run_ngspice.py', 'spice_scope.py', 'spice_probes.py']
SCOPE = ('Diagnostic native digital RX only, driven by every original restored-data '
         'and clock PWL knot. Original supplies, reset, PVT and output loads. '
         'Analog receivers, bias, driver and channel are omitted; ideal sources '
         'suppress analog loading feedback. Completion and agreement do not '
         'qualify the PHY or identify a failing device/solver mechanism.')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(wave, headers):
    t = wave[:, 1]
    if (len(t) < 2 or not np.isfinite(wave).all() or t[0] > 1e-15 or
            np.any(np.diff(t) <= 0)):
        raise ValueError('Incomplete or malformed recorded RX pins')
    # No compression, clipping, resampling, slew correction or thresholding.
    return '\n'.join('VREC_'+n+' '+n+' 0 PWL('+' '.join(
        f'{at:.17g} {v:.17g}' for at, v in zip(t, wave[:, headers['V('+n+')']]))+')'
        for n in NAMES[:2])+'\n'


def fixture(parent, out, stop):
    rows = ['OpenLVDS recorded-pin native digital RX isolation',
            f'.include "{out}/library.spice"', f'.include "{out}/pins.spice"']
    for pattern in [r'\.lib\s+.*', r'\.options device temp=.*', r'\.options timeint .*',
                    r'VDIG VDDD 0 1\.8', r'VRST RESET_N 0 .*',
                    r'XRX .* openlvds_ddr_rx', r'CQ0 Q0 0 20f', r'CQ1 Q1 0 20f']:
        matches = re.findall(r'(?m)^'+pattern+'$', parent)
        if len(matches) != 1:
            raise ValueError('Unexpected parent RX fixture row '+pattern)
        rows.extend(matches)
    rows.extend([f'.tran 5p {stop:.17g} 0 5p',
                 '.print tran '+' '.join('V('+n+')' for n in NAMES), '.end'])
    return '\n'.join(rows)+'\n'


def complete(wave, headers, stop):
    if (len(wave) < 2 or not np.isfinite(wave).all() or wave[0, 1] > 1e-15 or
            wave[-1, 1] < stop-1e-12 or np.any(np.diff(wave[:, 1]) <= 0) or
            any('V('+n+')' not in headers for n in NAMES)):
        raise ValueError('Incomplete native RX isolation waveform')


def compare(parent, ph, child, ch, start=50e-9, end=125e-9):
    if any(w[0, 1] > start or w[-1, 1] < end for w in [parent, child]):
        raise ValueError('Waveforms do not cover the comparison interval')
    result = {}
    for n in NAMES:
        a, b = parent[:, ph['V('+n+')']], child[:, ch['V('+n+')']]
        edges = {}
        for rising in [True, False]:
            old = edge_times(parent[:, 1], a, rising=rising)
            new = edge_times(child[:, 1], b, rising=rising)
            old, new = [v[(v >= start) & (v <= end)] for v in [old, new]]
            edges['rising' if rising else 'falling'] = dict(
                parent_count=len(old), replay_count=len(new),
                maximum_error_ps=float(np.max(abs(old-new))*1e12)
                    if len(old) == len(new) and len(old) else None)
        keep = (parent[:, 1] >= start) & (parent[:, 1] <= end)
        error = np.abs(a[keep]-np.interp(parent[keep, 1], child[:, 1], b))
        result[n] = dict(edges=edges, maximum_interpolated_voltage_error_v=float(error.max()))
    # Output constancy is handled separately from absence of transitions.
    for n in NAMES:
        r = result[n]
        r['edge_agreement_within_20ps'] = all(
            e['parent_count'] == e['replay_count'] and
            (e['parent_count'] == 0 or e['maximum_error_ps'] <= 20)
            for e in r['edges'].values())
    return dict(start_s=start, end_s=end, vectors=result,
                all_edge_counts_and_times_agree=all(r['edge_agreement_within_20ps'] for r in result.values()),
                scope='Comparison only; an unchanged wrong bit is still wrong. Voltage error uses interpolation and is reported separately from crossing agreement.')


def prepare(parent):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/analog_link_pilot'):
        raise ValueError('Use a completed selected-driver pilot in the pinned ngspice environment')
    # Remeasure the completed parent through its original frozen producer.
    pilot.run(parent)
    m = json.loads((parent/'manifest.json').read_text())
    report = json.loads((parent/'summary.json').read_text())
    if (report.get('diagnostic_complete') is not True or
            report['manifest_sha256'] != digest(parent/'manifest.json') or
            report['waveform_sha256'] != digest(parent/'bench.cir.prn') or
            provenance() != m['identity']['simulator_provenance']):
        raise ValueError('Parent completion or simulator evidence changed')
    wave, headers = read_wave(parent/'bench.cir.prn')
    original = (parent/'bench.cir').read_text()
    stop = number(re.search(r'(?im)^\.tran\s+\S+\s+(\S+)', original)[1])
    complete(wave, headers, stop)
    library = closure((parent/'library.spice').read_text(), [TOP])
    if closure_hash(library, TOP) != closure_hash((parent/'library.spice').read_text(), TOP):
        raise ValueError('Native RX closure changed')
    paths = [parent/n for n in ['manifest.json', 'summary.json', 'bench.cir', 'bench.cir.prn', 'library.spice']]
    identity = dict(parent=str(parent.relative_to(ROOT)), scope=SCOPE, stop_s=stop,
        config=m['identity']['config'], maximum_step_ps=5, simulator_provenance=provenance(),
        native_rx_closure_sha256=closure_hash(library, TOP), original_vertices=len(wave),
        inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
        code={n: digest(ROOT/'scripts'/n) for n in sorted(set(CODE) | set(m['identity']['code']))})
    root = ROOT/'build/diagnostics/native_rx_pin_replay'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    deck, pins = fixture(original, root, stop), sources(wave, headers)
    ProbeNetwork(library).validate(deck+pins, NAMES)
    root.mkdir(parents=True, exist_ok=True)
    for name, text in [('library.spice', library), ('pins.spice', pins), ('bench.cir', deck)]:
        p = root/name
        if p.exists() and p.read_text() != text:
            raise ValueError('Prepared native RX replay changed')
        if not p.exists():
            p.write_text(text)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False,
        files={n: digest(root/n) for n in ['library.spice', 'pins.spice', 'bench.cir']}))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/native_rx_pin_replay'):
        raise ValueError('Use a prepared native RX pin replay')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = digest(root/'manifest.json')
    def unchanged():
        if (digest(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                any(digest(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(digest(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(digest(root/n) != h for n, h in m['files'].items())):
            raise ValueError('Native RX pin replay context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((root/'summary.json').read_text()) if (root/'summary.json').exists() else None
        if cached is None:
            if any((root/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                raise ValueError('Partial native RX replay retained; use a fresh context')
            atomic(root/'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with lease(priority=1, label='native-digital-rx-recorded-pins'):
                unchanged(); atomic(root/'execution.json', dict(status='running', qualified_phy=False))
                p = subprocess.run(command(root/'ngspice.log', root/'bench.cir'), cwd=root, capture_output=True, text=True)
            (root/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
        elif digest(root/'bench.cir.prn') != cached['waveform_sha256']:
            raise ValueError('Completed native RX replay changed')
        unchanged()
        wave, headers = read_wave(root/'bench.cir.prn'); complete(wave, headers, i['stop_s'])
        pw, ph = read_wave(ROOT/i['parent']/'bench.cir.prn')
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp,
            waveform_sha256=digest(root/'bench.cir.prn'), comparison=compare(pw, ph, wave, headers), scope=SCOPE)
        unchanged()
        if cached is not None and cached != report:
            raise ValueError('Native RX replay remeasurement changed')
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
