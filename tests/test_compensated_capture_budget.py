from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_compensated_capture as diagnosis


class CompensatedCaptureBudget(unittest.TestCase):
    def waveforms(self):
        t = np.arange(0, 6.01, .01) * 1e-9
        clock = np.where(((t >= 1e-9) & (t < 3e-9)) | (t >= 5e-9), 1.8, 0)
        data = np.where(((t >= .2e-9) & (t < 2.2e-9)) | ((t >= 4.2e-9) & (t < 5.8e-9)), 1.8, 0)
        return t, data, clock

    def test_signed_common_interval_reproduces_setup_and_hold(self):
        result = diagnosis.budgets(*self.waveforms(), .5e-9, 4e-9, 200, 80, 200)
        self.assertEqual(len(result['records']), 2)
        self.assertEqual([r['edge'] for r in result['records']], ['rising', 'falling'])
        self.assertAlmostEqual(result['minimum_raw_setup_ps'], 800)
        self.assertAlmostEqual(result['minimum_raw_hold_ps'], 1200)
        self.assertAlmostEqual(result['minimum_setup_margin_ps'], 600)
        self.assertAlmostEqual(result['minimum_hold_margin_ps'], 1120)
        self.assertAlmostEqual(result['common_clock_shift']['interval_ps'][0], -400)
        self.assertAlmostEqual(result['common_clock_shift']['interval_ps'][1], 920)
        self.assertTrue(result['independent_midpoints_preserve_edge_order'])

    def test_more_demanding_aperture_can_make_common_shift_impossible(self):
        result = diagnosis.budgets(*self.waveforms(), .5e-9, 4e-9, 900, 900, 200)
        self.assertFalse(result['common_clock_shift']['nonempty'])
        self.assertIsNone(result['common_clock_shift']['midpoint_ps'])

    def test_separate_edge_intervals_cannot_masquerade_as_common_phase(self):
        rows = [dict(clock_ns=1, minimum_clock_shift_ps=100, maximum_clock_shift_ps=150),
                dict(clock_ns=2, minimum_clock_shift_ps=-150, maximum_clock_shift_ps=-100)]
        result = diagnosis.intersection(rows)
        self.assertFalse(result['nonempty'])
        self.assertEqual(result['interval_ps'], [100, -100])
        self.assertEqual(result['lower_witness_clock_ns'], 1)
        self.assertEqual(result['upper_witness_clock_ns'], 2)

    def test_missing_data_edges_and_clock_polarities_rejected(self):
        t, data, clock = self.waveforms()
        for args in [(t, np.zeros(len(t)), clock, .5e-9, 4e-9), (t, data, clock, .5e-9, 2e-9)]:
            with self.assertRaises(ValueError): diagnosis.budgets(*args, 200, 80, 200)

    def test_negative_nonfinite_aperture_rejected(self):
        for value in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError): diagnosis.budgets(*self.waveforms(), .5e-9, 4e-9, value, 80, 200)

    def test_final_held_bit_is_censored_without_inventing_an_edge(self):
        t, data, clock = self.waveforms()
        data[t >= 4.2e-9] = 1.8
        result = diagnosis.budgets(t, data, clock, .5e-9, 5.5e-9, 200, 80, 200)
        last = result['records'][-1]
        self.assertTrue(last['hold_right_censored'])
        self.assertIsNone(last['following_data_ns'])
        self.assertAlmostEqual(last['hold_observed_until_ns'], t[-1] * 1e9)
        self.assertAlmostEqual(result['minimum_raw_hold_ps'], 1200)

    def test_unverified_payload_cannot_supply_timing_evidence(self):
        with patch.object(diagnosis.coupled, 'verify', return_value=dict(payload_restored=False)):
            with self.assertRaises(ValueError): diagnosis.diagnose(Path('unverified'))
