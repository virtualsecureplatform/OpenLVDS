# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_dcdl_iterations_v3 as verifier


class FailedIterationBaselineTests(unittest.TestCase):
    def test_failed_baseline_is_retained_without_a_timing_equivalence_comparison(self):
        remeasure=Mock(side_effect=AssertionError('Incomplete raw must not be compared'))
        result=verifier.compare_available_baseline({},dict(error='Timestep too small',result=None),remeasure)
        self.assertEqual(result,dict(status='unavailable_due_to_baseline_error',error='Timestep too small'))
        remeasure.assert_not_called()
        with self.assertRaises(ValueError):verifier.compare_available_baseline({},dict(error='aborted',result={}),remeasure)

    def test_successful_baseline_requires_independent_matching_remeasurement(self):
        original=dict(samples=[dict(pulse=0,rise_delay_ps=100,fall_delay_ps=110)],terminal_stress=[dict(device='X0',max_terminal_difference_v=1.9)],native_pulse_passed=True)
        result=verifier.compare_available_baseline(original,dict(error=None,result=original),lambda:original)
        self.assertEqual(result['status'],'complete_independently_remeasured')
        self.assertEqual(result['maximum_absolute_edge_delay_difference_ps'],0)
        with self.assertRaisesRegex(ValueError,'remeasurement changed'):
            verifier.compare_available_baseline(original,dict(error=None,result=original),lambda:dict(original,native_pulse_passed=False))


if __name__=='__main__':unittest.main()
