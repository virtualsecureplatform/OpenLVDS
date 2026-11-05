# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_nlvt_guard2_sparse_v41 as pilot
import verify_nlvt_guard2_sparse_v41 as proof


class ReusedZeroSparseTests(unittest.TestCase):
    def receipt(self):
        rows=[];profiles=[]
        for spec in pilot.zero.specifications():
            passed=spec['profile']=='both2'
            r=dict(terminal_screen_passed=True,control_settling_passed=True,onehot_control_settling_passed=True,
                   zero_code_fast_quarter_headroom_ps=4.28 if passed else -13.,repeated_delay_difference_ps=dict(rise=0.,fall=0.))
            rows.append(dict(task=dict(spec=spec),result=r))
            profiles.append(dict(profile=spec['profile'],zero_code_native_gate_passed=passed,
                                 completed_sparse_points=1,all_sparse_points_present=False))
        return dict(identity=dict(terminal_cases_only=False),rows=rows,profiles=profiles,
                    all_consumed_complete_native_waveforms_verified=True,all_declared_cases_consumed=True,
                    qualified_phy=False,component_rc_physically_equivalent=True,whole_bank_rc_retained=False)

    def test_only_complete_positive_both2_gate_is_accepted(self):
        r=self.receipt();self.assertEqual(pilot.require_zero_pass(r)['task']['spec']['profile'],'both2')
        for value in [-1.,0.,float('nan'),float('inf')]:
            r=self.receipt();r['rows'][1]['result']['zero_code_fast_quarter_headroom_ps']=value
            with self.subTest(headroom=value),self.assertRaises(ValueError):pilot.require_zero_pass(r)
        for key,value in [('all_declared_cases_consumed',False),('component_rc_physically_equivalent',False),('qualified_phy',True)]:
            r=self.receipt();r[key]=value
            with self.subTest(fault=key),self.assertRaises(ValueError):pilot.require_zero_pass(r)
        r=self.receipt();r['identity']['terminal_cases_only']=True
        with self.assertRaises(ValueError):pilot.require_zero_pass(r)

    def test_failed_controls_repeatability_or_wrong_spec_are_rejected(self):
        for key in ('terminal_screen_passed','control_settling_passed','onehot_control_settling_passed'):
            r=self.receipt();r['rows'][1]['result'][key]=False
            with self.subTest(fault=key),self.assertRaises(ValueError):pilot.require_zero_pass(r)
        for differences in ({'rise':0.},{'rise':21.,'fall':0.},{'rise':float('nan'),'fall':0.}):
            r=self.receipt();r['rows'][1]['result']['repeated_delay_difference_ps']=differences
            with self.subTest(repeat=differences),self.assertRaises(ValueError):pilot.require_zero_pass(r)
        r=self.receipt();r['rows'][1]['task']['spec']['coarse']=1
        with self.assertRaises(ValueError):pilot.require_zero_pass(r)

    def test_five_new_codes_use_same_fixture_and_do_not_resimulate_zero(self):
        specs=pilot.specifications();self.assertEqual([(s['coarse'],s['fine']) for s in specs],list(pilot.CODES))
        self.assertNotIn((0,0),pilot.CODES)
        with patch.dict(os.environ,PDK_ROOT='/test/pdk'):
            before=pilot.zero.fixture(Path('/work/OpenLVDS/build/example'),specs[2],[])
            after=pilot.fixture(Path('/work/OpenLVDS/build/example'),specs[2],[])
        self.assertEqual(before.split('\n',1)[1],after.split('\n',1)[1])
        self.assertTrue(all(s['profile']=='both2' and s['process']=='ss' and s['temperature']==40 for s in specs))

    def rows(self):
        rows=[]
        for c,f in ((0,0),*pilot.CODES):
            result=dict(terminal_screen_passed=True,control_settling_passed=True,onehot_control_settling_passed=True,
                        repeated_delay_difference_ps=dict(rise=0,fall=0),zero_code_fast_quarter_headroom_ps=4.28,
                        samples=[dict(rise_delay_ps=511.+f*2+c*30,fall_delay_ps=605.+f*2+c*30)]*2)
            rows.append(dict(task=dict(spec=dict(pilot.specifications()[0],coarse=c,fine=f)),result=result))
        return rows

    def test_six_codes_carry_and_overlap_are_required_without_phy_admission(self):
        report=proof.comparisons(self.rows())[0]
        self.assertTrue(report['sparse_native_screen_passed']);self.assertEqual(report['completed_sparse_points'],6)
        self.assertFalse(report['qualified_phy']);self.assertFalse(report['dense_legal_code_coverage_proven'])
        self.assertFalse(proof.comparisons(self.rows()[1:])[0]['sparse_native_screen_passed'])
        broken=self.rows();broken[3]['result']['samples'][1]['rise_delay_ps']+=30
        self.assertFalse(proof.comparisons(broken)[0]['sparse_native_screen_passed'])
        broken=self.rows();broken[-1]['result']['samples'][1]['fall_delay_ps']+=100
        self.assertFalse(proof.comparisons(broken)[0]['sparse_native_screen_passed'])
        with self.assertRaises(ValueError):proof.comparisons(self.rows()+[deepcopy(self.rows()[0])])


if __name__=='__main__':unittest.main()
