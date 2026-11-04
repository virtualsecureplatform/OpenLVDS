# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_conditioned_clock_v2 import compare_result


class ConditionedClockVerificationTests(unittest.TestCase):
    def test_scope_is_descriptive_but_all_measurements_and_domains_are_bound(self):
        row=dict(scope='producer',pilot_passed=True,terminal_stress=[dict(limit_v=1.95,passed=True)],half_cycle_error_ps=17.)
        compare_result({**row,'scope':'verifier'},row)
        for changed in [dict(pilot_passed=False),dict(half_cycle_error_ps=17.01),dict(terminal_stress=[dict(limit_v=5.5,passed=True)])]:
            with self.assertRaises(ValueError):compare_result({**row,**changed},row)

    def test_missing_or_extra_measurements_are_rejected(self):
        with self.assertRaises(ValueError):compare_result(dict(passed=True),dict(passed=True,missing=False))


if __name__=='__main__':unittest.main()
