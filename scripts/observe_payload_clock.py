#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Freeze an available payload interval and locate clock loss without rescoring it."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from diagnose_native_dll_loop import raw_prefix
from diagnose_link_clock import pulse_transport
from observe_receiver_input_contract import pulse_support
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times

ROOT = Path(__file__).resolve().parents[1]
CODE = ['observe_payload_clock.py', 'diagnose_native_dll_loop.py',
        'diagnose_link_clock.py', 'observe_receiver_input_contract.py',
        'simulate_link.py', 'receiver_static_diagnosis.py']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def analyze(names, wave, start_ns, end_ns, threshold):
    t = wave[:, names.index('time')]
    start, end = start_ns * 1e-9, end_ns * 1e-9
    if not t[0] <= start < end <= t[-1]:
        raise ValueError('Complete observation interval unavailable')

    def v(name):
        return wave[:, names.index('v(' + name.lower() + ')')]

    differential = v('RCP') - v('RCN')
    transport = pulse_transport(t, differential, v('RXCLOCK'), start, end)
    pulses = pulse_support(t, differential, transport, threshold)
    for pulse in pulses:
        a = pulse['input_edge_ns'] * 1e-9
        b = a + pulse['input_pulse_width_ps'] * 1e-12
        local = np.r_[a, t[(t > a) & (t < b)], b]
        pulse['receiver_stages'] = {}
        for node in ['CO', 'CL', 'CT', 'RESTORE0', 'RESTORE1']:
            signal = np.interp(local, t, v('xcr.openlvds_receiver_core__' + node))
            pulse['receiver_stages'][node] = dict(min_v=float(signal.min()),
                                                 max_v=float(signal.max()))
    stages = {}
    for name, signal, level in [('tx_digital', v('TXCLOCK'), .9),
                               ('tx_differential', v('CP') - v('CN'), 0),
                               ('rx_differential', differential, 0),
                               ('rx_digital', v('RXCLOCK'), .9)]:
        stages[name] = {}
        crossing = {polarity: edge_times(t, signal, level, polarity)
                    for polarity in [True, False]}
        for polarity, label in [(True, 'rising'), (False, 'falling')]:
            events = crossing[polarity]
            stages[name][label + '_ns'] = (events[(events >= start) &
                                                          (events <= end)] * 1e9).tolist()
            widths = []
            for at in events:
                later = crossing[not polarity][crossing[not polarity] > at]
                if len(later) and start <= at < later[0] <= end:
                    widths.append(float((later[0] - at) * 1e12))
            stages[name][label + '_pulse_width_ps'] = widths
    return dict(stages=stages, receiver_transport=dict(transport, pulses=pulses))


def observe(source, start_ns, end_ns):
    if not source.is_relative_to(ROOT / 'build/diagnostics/baseline_payload_recovery'):
        raise ValueError('Use a baseline payload recovery artifact')
    inputs = {str((source / name).relative_to(ROOT)): digest((source / name).read_bytes())
              for name in ['manifest.json', 'bench.cir', 'library.spice']}
    manifest = json.loads((source / 'manifest.json').read_text())
    proofs = dict(manifest['identity']['inputs'])
    proofs.update({'scripts/' + name: value
                   for name, value in manifest['identity']['code'].items()})
    proofs.update({str((source / name).relative_to(ROOT)): value
                   for name, value in manifest['files'].items()})
    if any(digest((ROOT / name).read_bytes()) != value for name, value in proofs.items()):
        raise ValueError('Frozen payload evidence changed')
    inputs.update(proofs)
    inputs.update({'scripts/' + name: digest((ROOT / 'scripts' / name).read_bytes())
                   for name in CODE})
    inputs['requirements.json'] = digest((ROOT / 'requirements.json').read_bytes())

    def unchanged():
        if any(digest((ROOT / name).read_bytes()) != value for name, value in inputs.items()):
            raise ValueError('Payload observation context changed')

    unchanged()
    data = (source / 'bench.raw').read_bytes()
    names, wave, description = raw_prefix(data)
    threshold = json.loads((ROOT / 'requirements.json').read_text())['rx_threshold_v']
    result = analyze(names, wave, start_ns, end_ns, threshold)
    identity = dict(source=str(source.relative_to(ROOT)), inputs=inputs,
                    snapshot_sha256=digest(data), window_ns=[start_ns, end_ns])
    out = ROOT / 'build/diagnostics/payload_clock_observation' / digest(
        json.dumps(identity, sort_keys=True).encode())[:16]
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / 'snapshot.raw'
    if snapshot.exists():
        if digest(snapshot.read_bytes()) != digest(data):
            raise ValueError('Snapshot changed')
    else:
        snapshot.write_bytes(data)
    unchanged()
    capture_manifest(out / 'summary.json', dict(identity=identity,
        raw_description=description, sensitivity_threshold_v=threshold,
        qualified_phy=False, qualification_verdict=None, **result,
        scope='Immutable snapshot of an available fixed interval from the original '
              'native 110:1 driver / preferred r2 receiver / calibrated LTRA chain. '
              'The shaped source driver is not in this chain. Partial raw frames '
              'are ignored only by the snapshot reader. Pulse support and stage '
              'extrema describe observations, not dynamic sensitivity guarantees '
              'or final payload, training, aperture or PHY qualification. '
              'Original execution and terminal verdicts are unchanged.'))
    return out / 'summary.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--start-ns', type=float, default=60)
    parser.add_argument('--end-ns', type=float, default=95)
    args = parser.parse_args()
    print(observe(args.source.resolve(), args.start_ns, args.end_ns), flush=True)
