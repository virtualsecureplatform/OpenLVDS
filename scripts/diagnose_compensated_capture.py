#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure phase-shift budgets from the verified compensated payload trace.

Clock shifts are algebra on fixed crossings, not a simulated delay circuit.
The legacy aperture estimate is explicitly diagnostic and out of slew domain.
"""
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


def intersection(records):
    if not records:
        raise ValueError('Missing capture edges')
    lower = max(records, key=lambda r: r['minimum_clock_shift_ps'])
    upper = min(records, key=lambda r: r['maximum_clock_shift_ps'])
    lo, hi = lower['minimum_clock_shift_ps'], upper['maximum_clock_shift_ps']
    return dict(interval_ps=[lo, hi], nonempty=lo <= hi,
        midpoint_ps=(lo + hi) / 2 if lo <= hi else None,
        lower_witness_clock_ns=lower['clock_ns'], upper_witness_clock_ns=upper['clock_ns'])


def budgets(time, data, clock, first, last, setup_ps, hold_ps, margin_ps):
    if not np.isfinite([setup_ps, hold_ps, margin_ps]).all() or min(setup_ps, hold_ps, margin_ps) < 0:
        raise ValueError('Require finite nonnegative aperture and margin')
    transitions = edge_times(time, data)
    if not len(transitions):
        raise ValueError('Missing data transitions')
    captures = edge_times(time, clock)
    captures = captures[(captures >= first - 1e-15) & (captures < last - 1e-15)]
    rising = edge_times(time, clock, rising=True)
    records = []
    for at in captures:
        before, after = transitions[transitions < at], transitions[transitions > at]
        if not len(before) or at >= time[-1] or np.any(abs(transitions - at) <= 1e-18):
            raise ValueError('Missing or coincident bracketing data transitions')
        # The final payload bit can remain constant until trace end. Retain
        # that observation as a censored lower bound, never invent a transition.
        right_censored = not len(after)
        hold_end = after[0] if len(after) else time[-1]
        raw_setup, raw_hold = (at - before[-1]) * 1e12, (hold_end - at) * 1e12
        records.append(dict(clock_ns=float(at * 1e9), edge='rising' if np.any(abs(rising - at) < 1e-18) else 'falling',
            preceding_data_ns=float(before[-1] * 1e9), following_data_ns=None if right_censored else float(after[0] * 1e9),
            hold_right_censored=right_censored, hold_observed_until_ns=float(hold_end * 1e9),
            raw_setup_ps=float(raw_setup), raw_hold_ps=float(raw_hold),
            setup_margin_ps=float(raw_setup - setup_ps), hold_margin_ps=float(raw_hold - hold_ps),
            minimum_clock_shift_ps=float(setup_ps + margin_ps - raw_setup),
            maximum_clock_shift_ps=float(raw_hold - hold_ps - margin_ps)))
    by_edge = {edge: intersection([r for r in records if r['edge'] == edge]) for edge in ('rising', 'falling')}
    ordered = None
    if all(v['nonempty'] for v in by_edge.values()):
        shifted = [r['clock_ns'] * 1000 + by_edge[r['edge']]['midpoint_ps'] for r in records]
        ordered = all(b > a for a, b in zip(shifted, shifted[1:]))
    return dict(records=records, common_clock_shift=intersection(records), independent_edge_shifts=by_edge,
        independent_midpoints_preserve_edge_order=ordered,
        minimum_raw_setup_ps=min(r['raw_setup_ps'] for r in records),
        minimum_raw_hold_ps=min((r['raw_hold_ps'] for r in records if not r['hold_right_censored']), default=None),
        minimum_setup_margin_ps=min(r['setup_margin_ps'] for r in records),
        minimum_hold_margin_ps=min((r['hold_margin_ps'] for r in records if not r['hold_right_censored']), default=None))


def diagnose(parent):
    report = coupled.verify(parent)
    if report.get('payload_restored') is not True:
        raise ValueError('Require an independently verified restored payload')
    summary = json.loads((parent / 'summary.json').read_text())
    measurement = next(r['measurements']['payload'] for r in summary['results'] if r['task'] == 'payload')
    wave, h = coupled.baseline.completed_export(parent / 'payload', 188.049)
    t = wave[:, 1]; clock = wave[:, h['V(RXCLOCK)']]; data = wave[:, h['V(RXDATA)']]
    publication = measurement['first_payload_publication_ns'] * 1e-9
    rises = edge_times(t, clock, rising=True)
    earlier = rises[rises < publication - 1e-15]
    if not len(earlier):
        raise ValueError('Missing first payload capture pair')
    words = measurement['checked_bits'] // 2
    pubs = rises[rises >= publication - 1e-15]
    if len(pubs) < words:
        raise ValueError('Missing final payload publication')
    # Reproduce the frozen decoder's diagnostic estimates exactly before
    # calculating alternatives. No characterized aperture is claimed here.
    result = budgets(t, data, clock, earlier[-1], pubs[words - 1], 200, 80, 200)
    if (len(result['records']) != measurement['checked_bits'] or
            abs(result['minimum_setup_margin_ps'] - measurement['setup_margin_ps']) > 1e-6 or
            abs(result['minimum_hold_margin_ps'] - measurement['hold_margin_ps']) > 1e-6):
        raise ValueError('Per-edge budgets disagree with the verified decoder window')
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json',
        parent / 'payload/bench.raw', parent / 'payload/bench.cir.prn']
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT / 'scripts' / n) for n in (Path(__file__).name, 'simulate_link.py', 'restore_compensated_coupled.py')},
        aperture_estimate_ps=dict(setup=200, hold=80), additional_margin_ps=200)
    out = ROOT / 'build/diagnostics/compensated_capture_budget' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', dict(identity=identity, **result,
        capture_input_slew_ps=measurement['capture_input_slew_ps'],
        inside_existing_aperture_slew_domain=measurement['capture_aperture_slew_passed'],
        characterized_aperture=False, physical_admission=False, qualified_phy=False,
        scope='Conditional signed phase shifts of fixed crossings in the complete 32-bit diagnostic. '
              'Negative shifts mean phase advance. Separate edge shifts change duty cycle. '
              'The decoder legacy 200/80 ps aperture estimate is not qualification. '
              'A real circuit, waveform/load changes, publication timing, actual DLL phase, '
              'extended slew-domain aperture and full link qualification remain required.'))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    print(diagnose(p.parse_args().artifact.resolve()), flush=True)
