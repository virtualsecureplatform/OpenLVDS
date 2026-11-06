# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from regenerated_bank_periodic_measure_v67 import timing as clock_timing
from rx_deskew_periodic_timing_v316 import timing


def waves(mhz=410, duty=.6, delay=3500, slew=100):
    spec = dict(cycles=8, frequency_mhz=mhz, duty=duty, stop_ns=32, coarse=0, fine=0)
    period = 1e6 / mhz
    t = np.arange(0., 32001., 1.)
    def pulse(offset):
        v = np.zeros(len(t))
        for k in range(8):
            rise = 2100 + k * period + offset
            fall = rise + duty * period
            v += 1.8 * np.minimum(np.clip((t - rise) / slew + .5, 0, 1),
                np.clip((fall - t) / slew + .5, 0, 1))
        return v
    return t, pulse(0), pulse(delay), spec


class RXDeskewTimingTests(unittest.TestCase):
    def test_absolute_epoch_spans_multiple_periods_at_all_clock_points(self):
        for mhz in (390, 400, 410):
            for duty in (.4, .5, .6):
                for periods in (.2, 1.2, 3.):
                    with self.subTest(mhz=mhz, duty=duty, periods=periods):
                        delay = periods * 1e6 / mhz
                        t, inp, out, spec = waves(mhz, duty, delay)
                        r = timing(t, inp, out, spec, role='rx_deskew')
                        self.assertTrue(r['rx_deskew_250ps_interface_screen_passed'])
                        self.assertAlmostEqual(r['maximum_absolute_delay_ps'], delay, places=7)
                        for values in r['edge_delays_ps'].values():
                            self.assertEqual(len(values), 8)
                            self.assertTrue(all(abs(v - delay) < 1e-7 for v in values))
                        if periods >= 1:
                            self.assertFalse(clock_timing(t, inp, out, spec)['unwrapped_native_epoch_passed'])
                        self.assertFalse(r['zero_code_quarter_check_required'])
                        self.assertFalse(r['qualified_phy'])

    def test_dll_roles_cannot_use_multi_period_exception(self):
        t, inp, out, spec = waves()
        for role in ('dll', 'rx_dll', 'tx', '', None):
            with self.subTest(role=role), self.assertRaises(ValueError):
                timing(t, inp, out, spec, role=role)
        with self.assertRaises(TypeError):
            timing(t, inp, out, spec)
        self.assertFalse(clock_timing(t, inp, out, spec)['zero_code_quarter_passed'])

    def test_missing_pulse_and_truncated_epoch_are_rejected(self):
        t, inp, out, spec = waves()
        missing = out.copy(); missing[t < 7500] = 0
        self.assertFalse(timing(t, inp, missing, spec, role='rx_deskew')['rx_deskew_timing_screen_passed'])
        with self.assertRaises(ValueError):
            timing(t[1:], inp[1:], out[1:], spec, role='rx_deskew')
        with self.assertRaises(ValueError):
            timing(t[:-1], inp[:-1], out[:-1], spec, role='rx_deskew')
        # A correctly declared shorter capture still fails if delayed pulses
        # have not arrived; it cannot borrow events from another clock epoch.
        t, inp, out, spec = waves(delay=3 * 1e6 / 410)
        keep = t <= 25000
        r = timing(t[keep], inp[keep], out[keep], dict(spec, stop_ns=25), role='rx_deskew')
        self.assertFalse(r['all_input_output_pulses_present'])
        self.assertFalse(r['rx_deskew_timing_screen_passed'])

    def test_extra_pulse_or_high_startup_and_tail_fail(self):
        t, inp, out, spec = waves()
        extra = out.copy(); extra[(t > 500) & (t < 800)] = 1.8
        self.assertFalse(timing(t, inp, extra, spec, role='rx_deskew')['rx_deskew_timing_screen_passed'])
        for index in (0, -1):
            bad = out.copy(); bad[index] = .2
            self.assertFalse(timing(t, inp, bad, spec, role='rx_deskew')['rx_deskew_timing_screen_passed'])

    def test_original_slew_period_history_limits_are_retained(self):
        t, inp, out, spec = waves(slew=400)
        r = timing(t, inp, out, spec, role='rx_deskew')
        self.assertTrue(r['rx_deskew_timing_screen_passed'])
        self.assertFalse(r['rx_deskew_250ps_interface_screen_passed'])
        t, inp, out, spec = waves()
        # Move the last output pulse 30ps: both original 20ps limits must fail.
        start = 2100 + 7 * 1e6 / spec['frequency_mhz'] + 3500 - 100
        delayed = np.interp(t - 30, t, out)
        out[t > start] = delayed[t > start]
        r = timing(t, inp, out, spec, role='rx_deskew')
        self.assertFalse(r['period_screen_passed'])
        self.assertFalse(r['repeated_delay_screen_passed'])
        self.assertFalse(r['rx_deskew_timing_screen_passed'])

    def test_nonfinite_nonmonotone_wrong_domain_and_units_are_rejected(self):
        t, inp, out, spec = waves()
        for bad in (dict(spec, frequency_mhz=420), dict(spec, duty=.3), dict(spec, cycles=True)):
            with self.assertRaises(ValueError):
                timing(t, inp, out, bad, role='rx_deskew')
        for bad_t in (t / 1000, t[::-1], np.where(t == 1, np.nan, t)):
            with self.assertRaises(ValueError):
                timing(bad_t, inp, out, spec, role='rx_deskew')
        bad = out.copy(); bad[10] = np.inf
        with self.assertRaises(ValueError):
            timing(t, inp, bad, spec, role='rx_deskew')

    def test_leading_or_zero_delay_does_not_wrap_into_positive_delay(self):
        for delay in (-100, 0):
            t, inp, out, spec = waves(delay=delay)
            r = timing(t, inp, out, spec, role='rx_deskew')
            self.assertTrue(r['all_input_output_pulses_present'])
            self.assertFalse(r['unwrapped_native_epoch_passed'])
            self.assertFalse(r['rx_deskew_timing_screen_passed'])

    def test_original_input_stimulus_and_full_swing_cannot_be_omitted(self):
        t, inp, out, spec = waves()
        shifted = np.interp(t - 2, t, inp)
        r = timing(t, shifted, out, spec, role='rx_deskew')
        self.assertFalse(r['input_timing_stimulus_passed'])
        self.assertFalse(r['rx_deskew_timing_screen_passed'])
        missing = inp.copy(); missing[t < 4000] = 0
        r = timing(t, missing, out, spec, role='rx_deskew')
        self.assertFalse(r['all_input_full_swing_pulses_present'])
        self.assertFalse(r['rx_deskew_timing_screen_passed'])
        self.assertFalse(r['delay_range_qualified'])
        self.assertFalse(r['codebook_qualified'])


if __name__ == '__main__':
    unittest.main()
