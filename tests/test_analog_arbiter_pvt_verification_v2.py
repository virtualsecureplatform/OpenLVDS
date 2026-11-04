# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_analog_arbiter_pvt_v2 as verification


class ArbiterProofTests(unittest.TestCase):
    def rows(self):
        return [dict(task=dict(spec=dict(process=p,temperature=40,swap=s,
            reference_slew_ps=20,feedback_slew_ps=200,offset_ps=o)),error=None,
            result=dict(correct_sign_fraction=1,frontend_stress_passed=True,common_mode_passed=True))
            for p in ['ss','sf'] for s in [0,1] for o in [-20,20]]

    def test_each_process_and_swap_must_pass_its_own_bracket(self):
        rows=self.rows();self.assertTrue(all(g['source_sign_and_health_passed'] for g in verification.groups(rows)))
        rows[0]['result']['correct_sign_fraction']=0
        groups=verification.groups(rows)
        self.assertEqual(sum(not g['source_sign_and_health_passed'] for g in groups),1)
        bad=next(g for g in groups if not g['source_sign_and_health_passed'])
        self.assertEqual((bad['process'],bad['swap']),('ss',0))

    def test_missing_sign_duplicate_and_failed_health_never_grant_pass(self):
        initial=self.rows()[:2]
        variants=[initial[:1],initial+[copy.deepcopy(initial[0])]]
        for key in ['frontend_stress_passed','common_mode_passed']:
            rows=copy.deepcopy(initial);rows[0]['result'][key]=False;variants.append(rows)
        rows=copy.deepcopy(initial);rows[0].update(error='numerical failure',result=None);variants.append(rows)
        for rows in variants:
            self.assertFalse(verification.groups(rows)[0]['source_sign_and_health_passed'])
