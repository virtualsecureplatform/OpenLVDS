# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_gang_sparse_v131 as p


class MeasuredGangSparseScreenTests(unittest.TestCase):
    def result(self,rise,fall):
        return dict(samples=[dict(rise_delay_ps=rise,fall_delay_ps=fall) for _ in range(2)],static_native_screen_passed=True,output_slew_domain_passed=True)

    def rows(self):
        return [dict(spec=dict(coarse=c,fine=0),error=None,result=self.result(100+100*c,120+100*c)) for c in (0,1)]

    def test_three_points_clear_original_gates_without_admitting_phy(self):
        r=p.compare(self.rows(),self.result(230,250))
        self.assertEqual(r['coarse_overlap'],dict(rise_ps=30,fall_ps=30))
        self.assertTrue(r['measured_component_sparse_feasibility_passed'])
        self.assertTrue(r['complete_fine31_trace_consumed'])
        self.assertFalse(r['whole_bank_rc_retained']);self.assertFalse(r['qualified_phy'])

    def test_consumed_fine_failure_negative_overlap_and_first_pulse_quarter_failure_refuse_pass(self):
        fine=self.result(230,250);fine['output_slew_domain_passed']=False
        self.assertFalse(p.compare(self.rows(),fine)['measured_component_sparse_feasibility_passed'])
        self.assertFalse(p.compare(self.rows(),self.result(199,250))['measured_component_sparse_feasibility_passed'])
        rows=self.rows();rows[0]['result']['samples'][0]['rise_delay_ps']=700
        self.assertLess(p.compare(rows,self.result(230,250))['zero_code_fast_quarter_headroom_ps'],0)
        self.assertFalse(p.compare(rows,self.result(230,250))['measured_component_sparse_feasibility_passed'])
        self.assertIsNone(p.compare(rows[:1],self.result(230,250)))
        rows=self.rows();rows[1]['spec']['coarse']=0
        with self.assertRaisesRegex(ValueError,'coverage'):p.compare(rows,self.result(230,250))

    def test_fresh_zero_coarse_fixtures_reset_fine_and_preserve_full_original_stimulus(self):
        source=dict(p.zero.spec(),profile='b2',coarse=0,fine=31);specs=p.specifications(source)
        self.assertEqual(source['fine'],31)
        for k,s in enumerate(specs):
            self.assertEqual((s['coarse'],s['fine']),(k,0))
            self.assertEqual({n:v for n,v in s.items() if n not in ['coarse','fine']},{n:v for n,v in source.items() if n not in ['coarse','fine']})
            i=dict(model='/model.lib',ports=['IN','OUT','VPWR','VGND'],observations=dict(devices=[],controls=[]))
            text=p.fixture(Path('/fixture'),i,s)
            self.assertIn('.tran 2p 20n 0 2p',text);self.assertIn('VE0 E0 0 0',text);self.assertIn('VE30 E30 0 0',text)
            self.assertIn('VS0 S0 0 '+('1.8' if k else '0'),text)


if __name__=='__main__':unittest.main()
