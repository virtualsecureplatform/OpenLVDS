# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_dcdl_pwl_source_v2 import verdict


class SourceIsolationVerdictTests(unittest.TestCase):
    def test_numerical_completion_does_not_hide_a_native_electrical_failure(self):
        complete=dict(numerically_completed=True,actual_source_representation_passed=True,
                      native_result={'native_pulse_passed':False},native_measurement_error=None)
        r=verdict(complete,None);self.assertTrue(r['complete_waveform_verified']);self.assertFalse(r['native_pulse_screen_passed'])
        complete.update(native_result=None,native_measurement_error='missing output pulse')
        self.assertFalse(verdict(complete,None)['native_pulse_screen_passed'])

    def test_aborted_or_missing_waveform_cannot_be_promoted_to_completion(self):
        r=verdict(None,'terminal timestep collapse')
        self.assertFalse(r['complete_waveform_verified']);self.assertFalse(r['native_pulse_screen_passed'])
        self.assertTrue(r['terminal_numerical_failure_verified'])
        for result,error in [(None,None),({'numerically_completed':True},None),({'numerically_completed':True},'failed')]:
            with self.assertRaises(ValueError):verdict(result,error)


if __name__=='__main__':unittest.main()
