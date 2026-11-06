# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_balanced_joint_zero_v146 as p


class MeasuredJointZeroTests(unittest.TestCase):
    def result(self):return dict(samples=[dict(rise_delay_ps=500.,fall_delay_ps=540.) for _ in range(2)],static_native_screen_passed=True)
    def slews(self):return dict(rise=[200.,250.],fall=[210.,220.])

    def test_zero_requires_all_native_checks_both_pulses_quarter_and_original_slew_limit(self):
        r=p.assess(self.result(),self.slews());self.assertTrue(r['joint_rc_zero_screen_passed'])
        self.assertTrue(r['whole_bank_rc_retained']);self.assertFalse(r['qualified_phy']);self.assertFalse(r['all_pvt_covered'])
        native=self.result();native['static_native_screen_passed']=False
        self.assertFalse(p.assess(native,self.slews())['joint_rc_zero_screen_passed'])
        first=self.result();first['samples'][0]['fall_delay_ps']=700
        self.assertLess(p.assess(first,self.slews())['zero_code_fast_quarter_headroom_ps'],0)
        wide=self.slews();wide['rise'][0]=250.01
        self.assertFalse(p.assess(self.result(),wide)['joint_rc_zero_screen_passed'])
        incomplete=self.slews();incomplete['fall'].pop()
        self.assertFalse(p.assess(self.result(),incomplete)['joint_rc_zero_screen_passed'])

    def test_incomplete_or_invalid_native_epoch_is_refused(self):
        for samples in [self.result()['samples'][:1],[dict(rise_delay_ps=-1,fall_delay_ps=500.) for _ in range(2)],
                        [dict(rise_delay_ps=float('nan'),fall_delay_ps=500.) for _ in range(2)]]:
            with self.assertRaises(ValueError):p.assess(dict(self.result(),samples=samples),self.slews())

    def test_fixture_keeps_original_full_stimulus_and_every_rc_separated_probe(self):
        ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
        i=dict(spec=p.spec('b2'),top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
        text=p.fixture(Path('/fixture'),i)
        for expected in ['.tran 2p 20n 0 2p','VDD VDD 0 1.8','.options device temp=40','VS0 S0 0 0','VE30 E30 0 0',
                         'V(XD:drain.t0)','V(XD:gate.t1)','V(XD:control.t2)']:
            self.assertIn(expected,text)
        self.assertIn('OpenLVDS '+p.VERSION,text)
        self.assertNotIn('.ic ',text)


if __name__=='__main__':unittest.main()
