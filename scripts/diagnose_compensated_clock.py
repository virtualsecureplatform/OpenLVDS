#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Locate duty distortion in a complete, independently verified coupled trace."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import restore_compensated_coupled as coupled
from simulate_link import edge_times
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = coupled.sha


def stats(values):
    if not values or not np.isfinite(values).all():
        raise ValueError('Missing finite clock observations')
    return dict(count=len(values), min_ps=float(min(values)), max_ps=float(max(values)), mean_ps=float(np.mean(values)))


def stage(time, signal, level, start, end):
    events = {edge: edge_times(time, signal, level, edge == 'rising') for edge in ('rising', 'falling')}
    result = {}
    for edge, opposite, label in (('rising', 'falling', 'high'), ('falling', 'rising', 'low')):
        widths = []
        for at in events[edge]:
            later = events[opposite][events[opposite] > at]
            if len(later) and start <= at < later[0] <= end:
                widths.append(float((later[0] - at) * 1e12))
        result[label + '_width'] = stats(widths)
        result[edge + '_edges_ns'] = (events[edge][(events[edge] >= start) & (events[edge] <= end)] * 1e9).tolist()
    return result


def transport(time, source, source_level, target, target_level, start, end):
    result = {}; matched_all = True
    for rising, label in ((True, 'rising'), (False, 'falling')):
        inputs = edge_times(time, source, source_level, rising)
        outputs = edge_times(time, target, target_level, rising)
        records = []; seen = set()
        for at, next_at in zip(inputs[:-1], inputs[1:]):
            if at < start or next_at > end:
                continue
            matches = np.flatnonzero((outputs > at) & (outputs < next_at))
            if len(matches) != 1 or int(matches[0]) in seen:
                raise ValueError('Clock stage has missing, ambiguous or reused responses')
            seen.add(int(matches[0]))
            records.append(dict(input_ns=float(at * 1e9), output_ns=float(outputs[matches[0]] * 1e9),
                                latency_ps=float((outputs[matches[0]] - at) * 1e12)))
        result[label] = dict(latency=stats([r['latency_ps'] for r in records]), records=records)
        matched_all = matched_all and len(records) >= 20
    result['at_least_twenty_per_polarity'] = matched_all
    result['mean_high_width_change_ps'] = result['falling']['latency']['mean_ps'] - result['rising']['latency']['mean_ps']
    result['matching_rule'] = 'One causal same-polarity crossing before the next source crossing of that polarity; no response reuse.'
    return result


def analyze(wave, header):
    time = wave[:, 1]; v = lambda n: wave[:, header['V(' + n + ')']]
    start, end = 60e-9, 120e-9
    if time[0] > 0 or time[-1] < end or not np.isfinite(wave).all():
        raise ValueError('Incomplete clock-stage observation interval')
    signals = [('source_quadrature', v('CLK90'), .9), ('tx_digital', v('TXCLOCK'), .9),
        ('tx_differential', v('CP') - v('CN'), 0), ('rx_differential', v('RCP') - v('RCN'), 0),
        ('rx_digital', v('RXCLOCK'), .9)]
    stages = {label: stage(time, signal, level, start, end) for label, signal, level in signals}
    hops = {}
    for (first, source, sl), (last, target, tl) in zip(signals[:-1], signals[1:]):
        hops[first + '_to_' + last] = transport(time, source, sl, target, tl, start, end)
    return dict(stages=stages, propagation=hops, interval_ns=[60, 120])


def diagnose(parent):
    if coupled.verify(parent).get('payload_restored') is not True:
        raise ValueError('Require the independently verified restored coupled payload')
    wave, header = coupled.baseline.completed_export(parent / 'payload', 188.049)
    result = analyze(wave, header)
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json']
    paths += [parent / 'payload' / n for n in ('bench.cir', 'library.spice', 'bench.raw', 'bench.cir.prn')]
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT / 'scripts' / n) for n in (Path(__file__).name, 'simulate_link.py', 'restore_compensated_coupled.py')})
    out = ROOT / 'build/diagnostics/compensated_clock_stages' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', dict(identity=identity, **result, qualified_phy=False,
        scope='Read-only crossing/latency decomposition of the complete restored diagnostic. '
              'Digital crossings use 0.9 V; differential crossings use zero. '
              'Mean falling-minus-rising delay estimates high-pulse widening at each hop. '
              'Timing windows differ at hop boundaries; this is not a loop, duty corrector, aperture or PHY qualification.'))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    print(diagnose(p.parse_args().artifact.resolve()), flush=True)
