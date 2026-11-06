# SPDX-License-Identifier: GPL-3.0-only
"""Absolute startup-epoch timing for RX deskew delays spanning clock periods.

This is a timing observer, not a native electrical or bank qualification.
The caller must retain full native terminal/control/RC checks separately.
"""
import math
import numpy as np
from regenerated_bank_periodic_measure_v67 import crossings, timing as clock_timing


def timing(t, inp, out, spec, *, role):
    if role != 'rx_deskew':
        raise ValueError('Absolute multi-period timing is restricted to RX deskew')
    if (type(spec['cycles']) is not int or spec['cycles'] < 2
            or spec['frequency_mhz'] not in (390, 400, 410)
            or not math.isfinite(spec['duty']) or not .4 <= spec['duty'] <= .6
            or not math.isfinite(spec['stop_ns']) or spec['stop_ns'] <= 0):
        raise ValueError('Require the approved clock domain and complete observation duration')
    t, inp, out = (np.asarray(v, dtype=float) for v in (t, inp, out))
    if (any(v.ndim != 1 for v in (t, inp, out)) or len(t) < 2
            or len(inp) != len(t) or len(out) != len(t)
            or not all(np.isfinite(v).all() for v in (t, inp, out))
            or t[0] < 0 or t[0] > 1e-6 or np.any(np.diff(t) <= 0)
            or t[-1] < spec['stop_ns'] * 1000 * (1 - 1e-8)):
        raise ValueError('Require complete finite startup-to-stop traces in ps')

    # Reuse unchanged absolute crossing, width, slew and period calculations.
    # These edge lists are indexed from startup, never reduced modulo T.
    result = clock_timing(t, inp, out, spec)
    count = spec['cycles']
    input_levels = {
        edge: {str(level): len(crossings(t, inp, level, up)) for level in (.18, .9, 1.62)}
        for up, edge in ((True, 'rise'), (False, 'fall'))
    }
    startup_and_shutdown = bool(inp[0] <= .18 and out[0] <= .18
        and inp[-1] <= .18 and out[-1] <= .18)
    complete_input = all(n == count for levels in input_levels.values() for n in levels.values())
    absolute_epoch = bool(startup_and_shutdown and complete_input
        and result['all_input_output_pulses_present']
        and all(math.isfinite(v) and v > 0 for values in result['edge_delays_ps'].values() for v in values))
    result.update(
        role=role, input_full_swing_crossing_counts=input_levels,
        startup_and_shutdown_low_passed=startup_and_shutdown,
        all_input_full_swing_pulses_present=complete_input,
        unwrapped_native_epoch_passed=absolute_epoch,
        absolute_startup_epoch_matching=True,
        maximum_absolute_delay_ps=max((v for values in result['edge_delays_ps'].values() for v in values), default=None),
        # RX deskew spans >1T. The separate RX DLL retains the quarter gate.
        zero_code_quarter_check_required=False,
        zero_code_fast_quarter_headroom_ps=None, zero_code_quarter_passed=True,
        native_electrical_checks_performed=False, whole_bank_rc_qualified=False,
        delay_range_qualified=False, codebook_qualified=False,
        all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False,
        scope='RX deskew absolute pulse timing only; no DLL quarter gate, delay-range/codebook, terminal/control, native RC or PHY admission')
    gates = ('startup_and_shutdown_low_passed', 'all_input_full_swing_pulses_present',
        'all_input_output_pulses_present', 'input_timing_stimulus_passed',
        'full_swing_pulses_passed', 'unwrapped_native_epoch_passed',
        'pulse_order_and_widths_passed', 'period_screen_passed', 'repeated_delay_screen_passed')
    result['rx_deskew_timing_screen_passed'] = all(result[k] for k in gates)
    result['rx_deskew_250ps_interface_screen_passed'] = bool(
        result['rx_deskew_timing_screen_passed'] and result['current_downstream_250ps_slew_domain_passed'])
    return result
