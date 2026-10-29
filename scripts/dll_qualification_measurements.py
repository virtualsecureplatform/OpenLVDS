# SPDX-License-Identifier: GPL-3.0-only
"""Causal delay and exact/approximate waveform checks for DLL qualification."""
import numpy as np
from dll_measurements import column, edges


def marker_latency(wave, header, mhz, marker_ns):
    """Track one deliberately omitted pulse through all four delay sections.

    Periodic phase alone cannot distinguish a quarter cycle from 1.25 cycles.
    The omitted-pulse position records the unwrapped propagation delay.
    """
    period = 1e-6 / mhz
    t = wave[:, 1]
    marker = marker_ns * 1e-9
    missing = {}
    gaps = {}
    for name in ['PH0', 'PH90', 'PH180', 'PH270', 'FB']:
        times = edges(t, column(wave, header, name))
        width = np.diff(times)
        selected = np.flatnonzero((times[:-1] > marker - 2 * period) &
                                  (times[:-1] < marker + 6 * period) & (width > 1.7 * period))
        if len(selected) != 1:
            return dict(passed=False, error='Missing or ambiguous marker on ' + name)
        i = selected[0]
        if not 1.8 * period < width[i] < 2.2 * period:
            return dict(passed=False, error='Invalid marker width on ' + name)
        missing[name] = float(times[i] + period)
        gaps[name] = float(width[i] * 1e12)
    names = ['PH0', 'PH90', 'PH180', 'PH270', 'FB']
    sections = [(missing[b] - missing[a]) * 1e12 for a, b in zip(names, names[1:])]
    total = (missing['FB'] - missing['PH0']) * 1e12
    passed = all(abs(value - period * 250e9) < 100 for value in sections)
    return dict(passed=bool(passed), unwrapped_sections_ps=sections,
                unwrapped_total_ps=total, marker_gaps_ps=gaps)


def compare(full, full_header, approximation, fast_header, names, start_ns, end_ns):
    """Keep the existing 20ps crossing and 20mV plateau comparison limits."""
    if any(w[0, 1] > start_ns*1e-9 or w[-1, 1] < end_ns*1e-9-1e-12 for w in [full, approximation]):
        return dict(passed=False, error='Incomplete full/fast comparison interval')
    results = []
    sample = np.linspace(start_ns * 1e-9, end_ns * 1e-9, 8001)
    for name in names:
        a = column(full, full_header, name)
        b = column(approximation, fast_header, name)
        analog = name in ['CTRL', 'COPY', 'UF', 'DF']
        crossings = []
        for wave, value in [(full, a), (approximation, b)]:
            event = np.sort(np.concatenate([edges(wave[:, 1], value), edges(wave[:, 1], value, rising=False)]))
            event = event[(event > sample[0]) & (event < sample[-1])]
            crossings.append(event if not analog else np.array([]))
        ea, eb = crossings
        equal = len(ea) == len(eb)
        timing = float(np.max(abs(ea - eb)) * 1e12) if equal and len(ea) else 0 if equal else None
        av = np.interp(sample, full[:, 1], a)
        bv = np.interp(sample, approximation[:, 1], b)
        keep = np.ones(len(sample), dtype=bool)
        for at in np.concatenate(crossings):
            keep &= abs(sample - at) > 300e-12
        voltage = float(np.max(abs(av[keep] - bv[keep]))) if np.any(keep) else None
        ok = equal and timing is not None and timing <= 20 and voltage is not None and voltage <= .02
        results.append(dict(node=name, passed=bool(ok), crossings_full=len(ea), crossings_fast=len(eb),
                            edge_error_ps=timing, plateau_error_v=voltage))
    return dict(passed=all(r['passed'] for r in results), outputs=results)
