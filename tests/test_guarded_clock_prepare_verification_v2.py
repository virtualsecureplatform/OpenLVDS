# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_guarded_clock_prepare_v2 import assess,pilot


class GuardedPrepareVerificationTests(unittest.TestCase):
    def rows(self):
        return [dict(task=dict(spec=s),error=None,result=dict(counter_feasibility_passed=True,
            terminal_stress=[dict(max_terminal_difference_v=1.9)],margin_to_next_half_phase_ps=dict(prepare=500,public_release=300)))
            for s in pilot.specifications()]

    def test_both_stop_levels_and_duty_endpoints_are_required_per_geometry(self):
        rows=self.rows();self.assertTrue(all(g['source_counter_feasibility_passed'] for g in assess(rows)))
        with self.assertRaisesRegex(ValueError,'Incomplete'):assess(rows[:-1])
        rows[3]['result']['counter_feasibility_passed']=False
        self.assertFalse(assess(rows)[0]['source_counter_feasibility_passed'])

    def test_reproduced_event_failure_is_retained_without_admitting_failed_geometry(self):
        rows=self.rows();rows[0].update(error='public_release rising-event count',result=None)
        groups=assess(rows)
        self.assertFalse(groups[0]['source_counter_feasibility_passed'])
        self.assertTrue(groups[1]['source_counter_feasibility_passed'])
        self.assertEqual(groups[0]['measurement_errors'],['public_release rising-event count'])


if __name__=='__main__':unittest.main()
