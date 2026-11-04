# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_weighted_fine_bank_v2 import assess,pilot


class WeightedFineVerificationTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for spec in pilot.specifications():
            samples=[dict(code=code,rise_delay_ps=300+spec['coarse']*200+code*10,
                          fall_delay_ps=300+spec['coarse']*200+code*10) for code in spec['codes']]
            rows.append(dict(task=dict(spec=spec),result=dict(samples=samples,terminal_screen_passed=True,minimum_quarter_headroom_ps=300)))
        return rows

    def test_missing_cases_and_one_polarity_overlap_failure_are_not_passed(self):
        rows=self.rows();self.assertTrue(all(g['sparse_feasibility_passed'] for g in assess(rows)))
        with self.assertRaisesRegex(ValueError,'Incomplete'):assess(rows[:-1])
        rows[0]['result']['samples'][3]['fall_delay_ps']=450
        self.assertFalse(assess(rows)[0]['sparse_feasibility_passed'])

    def test_native_stress_and_quarter_headroom_remain_requirements(self):
        rows=self.rows();rows[0]['result']['minimum_quarter_headroom_ps']=-1
        self.assertFalse(assess(rows)[0]['sparse_feasibility_passed'])
        rows=self.rows();rows[3]['result']['terminal_screen_passed']=False
        self.assertFalse(assess(rows)[1]['sparse_feasibility_passed'])


if __name__=='__main__':unittest.main()
