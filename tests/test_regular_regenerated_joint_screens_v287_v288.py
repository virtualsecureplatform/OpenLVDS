# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regular_regenerated_joint_sparse_v287 as sparse
import probe_regular_regenerated_joint_periodic_v288 as periodic

class RoutedSparseTests(unittest.TestCase):
    def result(self,a,b,zero=False):
        return dict(samples=[dict(rise_delay_ps=a,fall_delay_ps=a+5),dict(rise_delay_ps=b,fall_delay_ps=b+5)],
            joint_rc_zero_screen_passed=zero,joint_rc_sparse_point_passed=True,whole_bank_rc_retained=True,zero_code_fast_quarter_headroom_ps=60)

    def test_both_epoch_and_conservative_overlap_are_required(self):
        zero=self.result(540,541,True)
        rows=[dict(spec=dict(coarse=0,fine=31),result=self.result(870,872),error=None),dict(spec=dict(coarse=1,fine=0),result=self.result(730,732),error=None)]
        self.assertTrue(sparse.compare(rows,zero)['joint_rc_sparse_feasibility_passed'])
        rows[0]['result']=self.result(700,715);rows[1]['result']=self.result(699,714)
        r=sparse.compare(rows,zero)
        self.assertTrue(all(v>0 for epoch in r['coarse_overlap_by_pulse'] for v in epoch.values()))
        self.assertLess(r['conservative_coarse_overlap_ps']['rise'],0)
        self.assertFalse(r['joint_rc_sparse_feasibility_passed'])

    def test_missing_reference_epoch_or_lost_whole_bank_rc_cannot_pass(self):
        zero=self.result(540,541,True)
        rows=[dict(spec=dict(coarse=0,fine=31),result=self.result(870,872),error=None),dict(spec=dict(coarse=1,fine=0),result=self.result(730,732),error=None)]
        bad=deepcopy(rows);bad[0]['result']['whole_bank_rc_retained']=False
        self.assertFalse(sparse.compare(bad,zero)['joint_rc_sparse_feasibility_passed'])
        zero['samples']=zero['samples'][:1]
        with self.assertRaisesRegex(ValueError,'both complete pulse epochs'):sparse.compare(rows,zero)

class RoutedPeriodicTests(unittest.TestCase):
    def rows(self):
        specs=periodic.specifications(periodic.native.spec());rows=[]
        for s in specs:
            delay={(0,0):540,(0,31):875,(1,0):730}[s['coarse'],s['fine']]
            rows.append(dict(spec=s,error=None,result=dict(whole_bank_rc_retained=True,periodic_transport_screen_passed=True,
                current_clock_interface_screen_passed=True,edge_delays_ps={edge:[delay+k*.1 for k in range(8)] for edge in ('rise','fall')})))
        return specs,rows

    def test_all_27_cases_and_eight_edge_histories_are_required(self):
        specs,rows=self.rows()
        self.assertEqual(len(specs),27)
        self.assertEqual({s['frequency_mhz'] for s in specs},{390,400,410})
        self.assertEqual({s['duty'] for s in specs},{.4,.5,.6})
        self.assertEqual({(s['coarse'],s['fine']) for s in specs},{(0,0),(0,31),(1,0)})
        r=periodic.compare(rows,specs);self.assertTrue(r['all_current_clock_interface_cases_passed']);self.assertFalse(r['all_pvt_covered'])
        self.assertIsNone(periodic.compare(rows[:-1],specs))
        bad=deepcopy(rows);bad[0]['result']['edge_delays_ps']['rise'].pop()
        self.assertFalse(periodic.compare(bad,specs)['all_current_clock_interface_cases_passed'])

    def test_cross_frequency_overlap_and_every_original_clock_gate_remain_required(self):
        specs,rows=self.rows();bad=deepcopy(rows)
        row=next(r for r in bad if r['spec']['coarse']==1)
        row['result']['edge_delays_ps']['rise']=[900]*8
        self.assertFalse(periodic.compare(bad,specs)['all_current_clock_interface_cases_passed'])
        bad=deepcopy(rows);bad[0]['result']['current_clock_interface_screen_passed']=False
        self.assertFalse(periodic.compare(bad,specs)['all_current_clock_interface_cases_passed'])
        with self.assertRaisesRegex(ValueError,'coverage'):periodic.compare(list(reversed(rows)),specs)

    def test_generated_input_has_eight_full_cycles_and_original_solver_settings(self):
        specs,_=self.rows();out=Path('/unused-fixture')
        i=dict(top='native_bank',ports=['IN','OUT','VPWR','VGND'],model='model.lib',observations=dict(devices=[],controls=[]))
        for s in specs:
            text=periodic.fixture(out,i,s)
            self.assertTrue(text.startswith('OpenLVDS '+periodic.VERSION+'\n'))
            self.assertEqual(text.count('tanh('),16)
            self.assertIn('.tran 2p 25n 0 2p',text)
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',text)

if __name__=='__main__':unittest.main()
