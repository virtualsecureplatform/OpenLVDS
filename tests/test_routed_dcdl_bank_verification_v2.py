# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_routed_dcdl_bank_v2 import assess,pilot


class RoutedBankRangeVerificationTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for spec in pilot.specifications():
            delay=(500 if spec['process']=='ss' else 200)+({(0,0):0,(0,31):200,(1,0):150}[(spec['coarse'],spec['fine'])])
            rows.append(dict(task=dict(spec=spec),result=dict(samples=[dict(rise_delay_ps=delay,fall_delay_ps=delay) for _ in range(2)],native_pulse_passed=True)))
        return rows

    def test_requires_both_pvts_and_preserves_negative_overlap(self):
        rows=self.rows();self.assertTrue(all(g['sparse_feasibility_passed'] for g in assess(rows)))
        with self.assertRaisesRegex(ValueError,'Incomplete'):assess(rows[:-1])
        rows[1]['result']['samples'][0]['fall_delay_ps']=600
        groups=assess(rows);self.assertFalse(groups[0]['sparse_feasibility_passed'])
        self.assertEqual(groups[0]['coarse0_fine31_to_coarse1_fine0_overlap_ps']['fall'],-50)

    def test_slow_minimum_and_failed_mos_screen_cannot_be_admitted(self):
        rows=self.rows();rows[0]['result']['samples'][1]['rise_delay_ps']=700
        self.assertFalse(assess(rows)[0]['sparse_feasibility_passed'])
        rows=self.rows();rows[4]['result']['native_pulse_passed']=False
        self.assertFalse(assess(rows)[1]['sparse_feasibility_passed'])


if __name__=='__main__':unittest.main()
