# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_routed_dcdl_bank_direct_v2 import assess,pilot


class DirectBankTimingCoverageTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for spec in pilot.specifications():
            delay=(450 if spec['process']=='ss' else 200)+({(0,0):0,(0,31):250,(1,0):150}[(spec['coarse'],spec['fine'])])
            rows.append(dict(task=dict(spec=spec),result=dict(samples=[dict(rise_delay_ps=delay,fall_delay_ps=delay)],native_pulse_passed=True)))
        return rows

    def test_minimum_code_at_maximum_input_slew_is_required(self):
        rows=self.rows();self.assertEqual(len(rows),7)
        self.assertEqual(rows[1]['task']['spec']['input_slew_ps'],250)
        self.assertTrue(all(g['sparse_feasibility_passed'] for g in assess(rows)))
        rows[1]['result']['samples'][0]['rise_delay_ps']=650
        self.assertFalse(assess(rows)[0]['sparse_feasibility_passed'])
        with self.assertRaisesRegex(ValueError,'Incomplete'):assess(rows[:1]+rows[2:])

    def test_maximum_slew_stress_is_checked_even_when_100ps_cases_pass(self):
        rows=self.rows();rows[1]['result']['native_pulse_passed']=False
        self.assertFalse(assess(rows)[0]['sparse_feasibility_passed'])


if __name__=='__main__':unittest.main()
