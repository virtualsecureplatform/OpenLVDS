# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerated_bank_dense_metrics_v65 as p


class NativeDenseFineTests(unittest.TestCase):
    def fixture(self):
        rows=[]
        for c,f in p.CODES:
            sample=dict(rise_delay_ps=500+8*f+200*c,fall_delay_ps=480+7*f+200*c)
            r=dict(samples=[sample.copy(),sample.copy()],terminal_screen_passed=True,
                   control_settling_passed=True,repeated_delay_difference_ps=dict(rise=0.,fall=0.))
            if (c,f)==(0,0):r['zero_code_fast_quarter_headroom_ps']=109.7560975609756
            rows.append(dict(spec=dict(coarse=c,fine=f),result=r,error=None))
        return rows

    def test_all_fine_codes_and_both_coarse_selections_are_required(self):
        r=p.compare(self.fixture());self.assertTrue(r['ss40_dense_fine_screen_passed'])
        self.assertEqual(r['completed_dense_points'],64);self.assertEqual(len(r['dense_fine_steps']),124)
        self.assertEqual(len(p.FRESH_CODES),58);self.assertEqual(set(p.CODES)-set(p.FRESH_CODES),set(p.sparse.CODES))
        for key in ('all_pvt_covered','full_coarse_range_covered','legal_code_table_admitted','qualified_phy'):
            self.assertFalse(r[key])
        self.assertFalse(p.compare(self.fixture()[:-1])['ss40_dense_fine_screen_passed'])

    def test_reversal_between_sparse_samples_is_detected(self):
        rows=self.fixture()
        for sample in rows[8]['result']['samples']:sample['rise_delay_ps']=555
        r=p.compare(rows)
        self.assertTrue(r['inherited_sparse_comparison']['sparse_native_screen_passed'])
        self.assertFalse(r['all_adjacent_fine_gaps_passed']);self.assertFalse(r['ss40_dense_fine_screen_passed'])

    def test_large_gap_in_second_coarse_selection_is_detected(self):
        rows=self.fixture()
        for sample in rows[40]['result']['samples']:sample['fall_delay_ps']=750
        self.assertFalse(p.compare(rows)['ss40_dense_fine_screen_passed'])

    def test_all_native_screens_and_repeatability_remain_required(self):
        for key in ('terminal_screen_passed','control_settling_passed'):
            rows=self.fixture();rows[7]['result'][key]=False
            self.assertFalse(p.compare(rows)['ss40_dense_fine_screen_passed'])
        rows=self.fixture();rows[7]['result']['repeated_delay_difference_ps']['rise']=21
        self.assertFalse(p.compare(rows)['ss40_dense_fine_screen_passed'])

    def test_duplicate_invalid_or_incomplete_native_evidence_is_rejected(self):
        rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'Duplicate'):p.compare(rows+[rows[0]])
        for value in (float('nan'),float('inf'),-1):
            bad=deepcopy(rows);bad[7]['result']['samples'][0]['fall_delay_ps']=value
            with self.assertRaisesRegex(ValueError,'Invalid'):p.compare(bad)
        rows[7]['error']='incomplete'
        with self.assertRaisesRegex(ValueError,'Incomplete'):p.compare(rows)


if __name__=='__main__':unittest.main()
