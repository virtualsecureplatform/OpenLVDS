from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_compensated_clock as diagnosis


class ClockStageDiagnosis(unittest.TestCase):
    def signals(self):
        t = np.arange(0, 125.001, .005) * 1e-9
        source = 1.8 * ((t % 2.5e-9) < 1.25e-9)
        # Rising response is 100 ps late, falling response 300 ps late.
        target = 1.8 * (((t - .1e-9) % 2.5e-9) < 1.45e-9)
        return t, source, target

    def test_rising_and_falling_latency_locate_pulse_widening(self):
        t, source, target = self.signals()
        result = diagnosis.transport(t, source, .9, target, .9, 60e-9, 120e-9)
        self.assertTrue(result['at_least_twenty_per_polarity'])
        self.assertAlmostEqual(result['rising']['latency']['mean_ps'], 100, delta=5)
        self.assertAlmostEqual(result['falling']['latency']['mean_ps'], 300, delta=5)
        self.assertAlmostEqual(result['mean_high_width_change_ps'], 200, delta=5)

    def test_differential_zero_and_digital_midrail_report_same_crossings(self):
        t, source, _ = self.signals()
        digital = diagnosis.stage(t, source, .9, 60e-9, 120e-9)
        analog = diagnosis.stage(t, (source - .9) / 3, 0, 60e-9, 120e-9)
        for key in ('high_width', 'low_width'):
            self.assertAlmostEqual(digital[key]['mean_ps'], analog[key]['mean_ps'])

    def test_missing_or_multiple_outputs_cannot_form_a_latency_measurement(self):
        t, source, target = self.signals()
        for changed in (np.zeros(len(t)), 1.8 * ((t % 1.25e-9) < .625e-9)):
            with self.assertRaises(ValueError): diagnosis.transport(t, source, .9, changed, .9, 60e-9, 120e-9)

    def test_incomplete_payload_cannot_create_diagnosis(self):
        with patch.object(diagnosis.coupled, 'verify', return_value=dict(payload_restored=False)):
            with self.assertRaises(ValueError): diagnosis.diagnose(Path('unverified'))
