# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerated_bank_sparse_metrics_v63 as p


class RoutedSparseLimitsTests(unittest.TestCase):
    def fixture(self):
        rows=[]
        for c,f in p.CODES:
            sample=dict(rise_delay_ps=500+8*f+200*c,fall_delay_ps=480+7*f+200*c)
            result=dict(samples=[sample.copy(),sample.copy()],terminal_screen_passed=True,
                control_settling_passed=True,repeated_delay_difference_ps=dict(rise=0.,fall=0.))
            if (c,f)==(0,0):result['zero_code_fast_quarter_headroom_ps']=109.7560975609756
            rows.append(dict(spec=dict(coarse=c,fine=f),result=result,error=None))
        return rows

    def test_six_points_pass_without_admitting_dense_codes(self):
        r=p.compare(self.fixture());self.assertTrue(r['sparse_native_screen_passed'])
        self.assertEqual(r['coarse_overlap'],dict(rise_ps=48,fall_ps=17))
        self.assertEqual(len(r['fine_steps']),8)
        self.assertFalse(r['dense_legal_code_coverage_proven']);self.assertFalse(r['legal_code_table_admitted'])
        self.assertFalse(r['qualified_phy'])

    def test_carry_reversal_and_large_adjacent_gap_fail(self):
        for value in (610,650):
            rows=self.fixture()
            for sample in rows[3]['result']['samples']:sample['rise_delay_ps']=value
            self.assertFalse(p.compare(rows)['sparse_native_screen_passed'])

    def test_coarse_overlap_must_be_positive_on_both_edges(self):
        rows=self.fixture()
        for s in rows[-1]['result']['samples']:s['fall_delay_ps']=800
        self.assertFalse(p.compare(rows)['coarse_overlap_passed'])
        self.assertFalse(p.compare(rows)['sparse_native_screen_passed'])

    def test_missing_point_and_bad_native_gates_fail(self):
        rows=self.fixture();self.assertFalse(p.compare(rows[:-1])['sparse_native_screen_passed'])
        for key in ('terminal_screen_passed','control_settling_passed'):
            bad=deepcopy(rows);bad[1]['result'][key]=False
            self.assertFalse(p.compare(bad)['sparse_native_screen_passed'])
        bad=deepcopy(rows);bad[1]['result']['repeated_delay_difference_ps']['fall']=21
        self.assertFalse(p.compare(bad)['sparse_native_screen_passed'])
        rows[0]['result']['zero_code_fast_quarter_headroom_ps']=-1
        self.assertFalse(p.compare(rows)['sparse_native_screen_passed'])

    def test_duplicate_incomplete_and_nonfinite_evidence_is_rejected(self):
        rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'Duplicate'):p.compare(rows+[rows[0]])
        for value in (float('nan'),float('inf'),-1):
            bad=deepcopy(rows);bad[1]['result']['samples'][0]['rise_delay_ps']=value
            with self.assertRaisesRegex(ValueError,'Invalid'):p.compare(bad)
        rows[1]['error']='solver incomplete'
        with self.assertRaisesRegex(ValueError,'Incomplete'):p.compare(rows)


if __name__=='__main__':unittest.main()
