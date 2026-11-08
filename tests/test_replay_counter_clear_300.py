# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_counter_clear_300 as p

class ClearReplayTests(unittest.TestCase):
    def test_original_source_and_stimulus_establish_three_ns(self):
        allowance,paths=p.legacy_allowance();self.assertEqual(allowance,3000);self.assertEqual(len(paths),4)
    def test_no_stress_or_other_gate_can_change(self):
        old=dict(terminal_screen_passed=False,stopped_clock_arm_clear_passed=False)
        new=dict(old,stopped_clock_arm_clear_passed=True,stopped_clock_clear_start_ps=31000,stopped_clock_clear_settling_ps=3000)
        p.unchanged_metrics(old,new)
        new['terminal_screen_passed']=True
        with self.assertRaises(ValueError):p.unchanged_metrics(old,new)
    def test_does_not_allow_an_arbitrary_later_deadline(self):
        old=dict(stopped_clock_arm_clear_passed=False)
        new=dict(old,stopped_clock_clear_start_ps=33000,stopped_clock_clear_settling_ps=5000)
        with self.assertRaises(ValueError):p.unchanged_metrics(old,new)
