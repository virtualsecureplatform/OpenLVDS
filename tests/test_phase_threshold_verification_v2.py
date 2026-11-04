# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_phase_threshold_v2 as proof


class SignedThresholdProofTests(unittest.TestCase):
    def rows(self):
        return [dict(task=dict(spec=dict(reference_slew_ps=20,feedback_slew_ps=200,positive_offset=d,offset_ps=o)),
            error=None,result=dict(correct_sign_fraction=1,frontend_stress_passed=True,common_mode_passed=True))
            for d in [0,1] for o in [-20,0,20]]

    def test_each_polarity_requires_its_own_zero_and_two_outer_signs(self):
        rows=self.rows();self.assertTrue(all(g['source_threshold_and_health_passed'] for g in proof.groups(rows)))
        rows.pop(1)
        groups=proof.groups(rows)
        self.assertFalse(groups[0]['source_threshold_and_health_passed']);self.assertTrue(groups[1]['source_threshold_and_health_passed'])

    def test_phase_success_cannot_waive_reference_or_device_failure(self):
        for key in ['frontend_stress_passed','common_mode_passed','correct_sign_fraction']:
            rows=self.rows();rows[1]['result'][key]=False
            self.assertFalse(proof.groups(rows)[0]['source_threshold_and_health_passed'])
