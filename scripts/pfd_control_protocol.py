# SPDX-License-Identifier: GPL-3.0-only
"""Reset/disable protocol for the loaded PFD, with observed pin/clock checks."""
import re
import numpy as np
from dll_measurements import column, edges

VERSION = 'pfd-reset-enable-v1'
RESET = 'VRST RST 0 PWL(0 0 2n 0 2.02n 1.8 30.2n 1.8 30.22n 0 35.2n 0 35.22n 1.8)'
ENABLE = 'VEN ENABLE 0 PWL(0 0 10.2n 0 10.22n 1.8 15.2n 1.8 15.22n 0 25.2n 0 25.22n 1.8)'
EXPECTED = {'RST': {True: (2.01, 35.21), False: (30.21,)},
            'ENABLE': {True: (10.21, 25.21), False: (15.21,)}}


def apply(deck):
    if re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 5p 160n 0 20p']:
        raise ValueError('Require the original complete native phase timing')
    resets = re.findall(r'(?im)^VRST RST 0 PWL\([^\n]+\)$', deck)
    instances = re.findall(r'(?m)^XP (\S+) (\S+) RST VDDD UP DN VDDD 0 lvds_pfd$', deck)
    printed = re.findall(r'(?im)^\.print tran[^\n]+', deck)
    if (len(resets) != 1 or len(instances) != 1 or len(printed) != 1 or
            instances[0] not in [('REF', 'FDB'), ('REF_FAST', 'FDB_FAST')] or
            re.search(r'(?im)^VEN\b', deck) or re.search(r'(?i)V\((?:RST|ENABLE)\)', printed[0])):
        raise ValueError('Require the unmodified eight-port PFD phase/control fixture')
    result = deck.replace(resets[0], RESET + '\n' + ENABLE)
    before = 'XP ' + ' '.join(instances[0]) + ' RST VDDD UP DN VDDD 0 lvds_pfd'
    result = result.replace(before, before.replace('RST VDDD UP DN', 'RST ENABLE UP DN'))
    return result.replace(printed[0], printed[0] + ' V(RST) V(ENABLE)')


def measure(wave, header, mhz, clock_names=('REF', 'FDB')):
    if (wave.ndim != 2 or len(wave) < 2 or not np.isfinite(wave).all() or
            wave[0, 1] > 1e-15 or wave[-1, 1] < 160e-9 - 1e-12 or
            np.any(np.diff(wave[:, 1]) <= 0) or mhz not in (390, 400, 410)):
        raise ValueError('Require the complete finite fixed-rail control protocol')
    if not clock_names or len(set(clock_names)) != len(clock_names): raise ValueError('Require distinct actual clock observations')
    time = wave[:, 1]; signals = {n: column(wave, header, n) for n in ('RST', 'ENABLE', 'UP', 'DN', *clock_names)}
    timing = {}; correct = True
    for name, transitions in EXPECTED.items():
        records = {}
        for rising, targets in transitions.items():
            observed = edges(time, signals[name], rising=rising) * 1e9
            error = float(np.max(abs(observed - targets)) * 1000) if len(observed) == len(targets) else None
            passed = error is not None and error <= 5
            correct = correct and passed
            records['rising' if rising else 'falling'] = dict(observed_ns=list(map(float, observed)),
                                                            max_error_ps=error, passed=bool(passed))
        timing[name] = records
    half_period_ns = 500 / mhz
    windows = [('initial_disable', 5.2, 10.1, 'ENABLE'),
               ('dynamic_disable', 15.21 + half_period_ns, 25.1, 'ENABLE'),
               ('dynamic_reset', 30.21 + half_period_ns, 35.1, 'RST')]
    checks = []
    for name, start, end, control in windows:
        keep = (time > start * 1e-9) & (time < end * 1e-9)
        if not np.any(keep): raise ValueError('Missing scored reset/disable window')
        pin_low = float(signals[control][keep].max()) < .36
        up = float(signals['UP'][keep].max()); dn = float(signals['DN'][keep].max())
        clocks = {}
        for clk in clock_names:
            counts = []
            for rising in (True, False):
                at = edges(time, signals[clk], rising=rising)
                counts.append(int(((at > start * 1e-9) & (at < end * 1e-9)).sum()))
            swinging = bool(signals[clk][keep].min() < .36 and signals[clk][keep].max() > 1.44)
            clocks[clk] = dict(rising_events=counts[0], falling_events=counts[1], valid_levels=swinging,
                               passed=bool(min(counts) >= 1 and swinging))
        passed = bool(pin_low and up < .36 and dn < .36 and all(c['passed'] for c in clocks.values()))
        checks.append(dict(name=name, start_ns=start, end_ns=end, control_pin_low=pin_low,
                           up_max_v=up, dn_max_v=dn, clocks=clocks, passed=passed))
        correct = correct and passed
    keep = (time > 120e-9) & (time < 160e-9)
    released = bool(np.any(keep) and all(signals[n][keep].min() > 1.44 for n in ('RST', 'ENABLE')))
    return dict(passed=bool(correct and released), version=VERSION, timing=timing, windows=checks,
                controls_released_in_phase_window=released,
                scope='Observed control edges and reset/disable clearance under continuously running clocks. Phase-health recovery and electrical qualification are separate checks.')
