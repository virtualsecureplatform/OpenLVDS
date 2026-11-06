# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_balanced_joint_sparse_v153 as p


class JointSparseTests(unittest.TestCase):
    def result(self,rise,fall):
        return dict(samples=[dict(rise_delay_ps=rise,fall_delay_ps=fall) for _ in range(2)],
                    joint_rc_sparse_point_passed=True,whole_bank_rc_retained=True)

    def cases(self):
        return [dict(spec=s,result=self.result(*delay),error=None) for s,delay in zip(p.specifications(p.native.spec('b2')),[(690,850),(630,690)])]

    def zero(self):
        return dict(self.result(450,500),joint_rc_zero_screen_passed=True,zero_code_fast_quarter_headroom_ps=109.)

    def test_both_epochs_both_edges_and_full_bank_are_required(self):
        rows=self.cases();z=self.zero()
        self.assertTrue(p.compare(rows,z)['joint_rc_sparse_feasibility_passed'])
        for edge in ('rise','fall'):
            changed=deepcopy(rows);changed[0]['result']['samples'][0][edge+'_delay_ps']=600
            self.assertFalse(p.compare(changed,z)['joint_rc_sparse_feasibility_passed'])
        for index in (0,1):
            changed=deepcopy(rows);changed[index]['result']['joint_rc_sparse_point_passed']=False
            self.assertFalse(p.compare(changed,z)['joint_rc_sparse_feasibility_passed'])
        changed=deepcopy(rows);changed[0]['result']['whole_bank_rc_retained']=False
        self.assertFalse(p.compare(changed,z)['joint_rc_sparse_feasibility_passed'])
        z['joint_rc_zero_screen_passed']=False
        self.assertFalse(p.compare(rows,z)['joint_rc_sparse_feasibility_passed'])
        self.assertFalse(p.compare(rows,z)['qualified_phy'])

    def test_missing_duplicate_invalid_or_errored_case_cannot_pass(self):
        rows=self.cases();self.assertIsNone(p.compare(rows[:1],self.zero()))
        rows[0]['error']='incomplete trace';self.assertIsNone(p.compare(rows,self.zero()))
        rows=self.cases();rows[1]['spec']=rows[0]['spec']
        with self.assertRaises(ValueError):p.compare(rows,self.zero())
        rows=self.cases();rows[0]['result']['samples'].pop()
        with self.assertRaises(ValueError):p.compare(rows,self.zero())
        rows=self.cases();rows[0]['result']['samples'][0]['rise_delay_ps']=float('inf')
        with self.assertRaises(ValueError):p.compare(rows,self.zero())

    def test_only_zero_has_quarter_budget_nonzero_keeps_native_and_slew_gates(self):
        native=dict(self.result(690,850),zero_code_fast_quarter_headroom_ps=-240.,joint_rc_zero_screen_passed=False,
                    static_native_screen_passed=True,output_slew_domain_passed=True)
        with patch.object(p.native,'measure',return_value=native):r=p.measure(Path('/case'),{})
        self.assertTrue(r['joint_rc_sparse_point_passed']);self.assertNotIn('joint_rc_zero_screen_passed',r)
        for key in ('static_native_screen_passed','output_slew_domain_passed'):
            changed=dict(native,zero_code_fast_quarter_headroom_ps=-240.,joint_rc_zero_screen_passed=False);changed[key]=False
            with patch.object(p.native,'measure',return_value=changed):self.assertFalse(p.measure(Path('/case'),{})['joint_rc_sparse_point_passed'])

    def test_fixture_preserves_native_stimulus_rc_probes_and_selected_codes(self):
        ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
        i=dict(spec=p.native.spec('b2'),top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
        for s in p.specifications(i['spec']):
            text=p.fixture(Path('/fixture'),i,s)
            expected=p.native.fixture(Path('/fixture'),dict(i,spec=s)).replace('OpenLVDS '+p.native.VERSION,'OpenLVDS '+p.VERSION,1)
            self.assertEqual(text,expected)
            for value in ('.tran 2p 20n 0 2p','VDD VDD 0 1.8','V(XD:drain.t0)','V(XD:gate.t1)','V(XD:control.t2)'):
                self.assertIn(value,text)
            self.assertNotIn('.ic ',text)
        self.assertEqual([(s['coarse'],s['fine']) for s in p.specifications(i['spec'])],[(0,31),(1,0)])


if __name__=='__main__':unittest.main()
