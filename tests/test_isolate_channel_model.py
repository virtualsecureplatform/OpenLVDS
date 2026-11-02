# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolate_channel_model as channel
from reduce_rc import number


class DelayedChannelIsolation(unittest.TestCase):
    def deck(self):
        return '''Title
.include "/old/library.spice"
.options reltol=1e-4 abstol=1e-12 method=gear
VDD VDDD 0 1.8
TD0 D0B 0 D0F 0 Z0=50 TD=1.3n
TD1 D1B 0 D1F 0 Z0=50 TD=1.3n
TC0 C0B 0 C0F 0 Z0=50 TD=1.2n
TC1 C1B 0 C1F 0 Z0=50 TD=1.2n
CPAD C0B 0 2p
LPKG C0F RCP 1n
RTERM D0F D1F 100
.tran 1p 12n 0 1p
.print tran V(RCP)
.end
'''

    def test_ltra_preserves_impedance_and_each_original_delay(self):
        deck,ports=channel.fixture(self.deck(),Path('/old'),Path('/new'),'ltra_lossless')
        models=[line.split()[3:] for line in deck.splitlines() if line.startswith('.model')]
        self.assertEqual(len(models),4)
        for p,words in zip(ports,models):
            params={k:number(v) for k,v in (word.split('=') for word in words)}
            self.assertEqual(params['R'],0);self.assertEqual(params['G'],0);self.assertEqual(params['LEN'],1)
            self.assertAlmostEqual(np.sqrt(params['L']/params['C']),p['z0_ohm'],places=10)
            self.assertAlmostEqual(np.sqrt(params['L']*params['C'])/p['delay_s'],1,places=12)
        for line in self.deck().splitlines()[1:]:
            if not line.startswith(('T','.include')):self.assertIn(line,deck)

    def test_zero_delay_changes_only_four_line_elements_and_include(self):
        result,_=channel.fixture(self.deck(),Path('/old'),Path('/new'),'zero_delay')
        for line in ['VZERO_TD0 D0B D0F 0','VZERO_TC1 C1B C1F 0']:self.assertIn(line,result)
        self.assertEqual(sum(line.startswith('VZERO_') for line in result.splitlines()),4)
        for line in self.deck().splitlines()[1:]:
            if not line.startswith(('T','.include')):self.assertIn(line,result)

    def test_changed_delay_nodes_or_accuracy_cannot_enter_bounded_control(self):
        for bad in [self.deck().replace('TD=1.2n','TD=1.1n'),self.deck().replace('C0B 0 C0F','OTHER 0 C0F'),
                    self.deck().replace('0 1p','0 20p'),self.deck().replace('TD1 D1B','TOTHER D1B')]:
            with self.assertRaises(ValueError):channel.fixture(bad,Path('/old'),Path('/new'),'ltra_lossless')

    def test_calibration_requires_model_agreement_and_analytic_matched_delay(self):
        t=np.linspace(0,12e-9,12001);src=np.where(t<3e-9,.2,.6)
        expected=np.interp(t-1.2e-9,t,src)/2
        w=np.column_stack([np.arange(len(t)),t,src,expected,expected]);h={'V(SRC)':2,'V(OUT_T)':3,'V(OUT_O)':4}
        self.assertTrue(channel.calibrated(w,h,50)['passed'])
        bad=w.copy();bad[:,4]+=.002;self.assertFalse(channel.calibrated(bad,h,50)['passed'])
        bad=w.copy();bad[:,3]=bad[:,4]=np.interp(t-1.3e-9,t,src)/2
        self.assertFalse(channel.calibrated(bad,h,50)['passed'])
        with self.assertRaises(ValueError):channel.calibrated(w[:-10],h,50)

    def test_reflective_controls_and_matched_control_are_distinct(self):
        self.assertIn('RT SRC IN_T 10',channel.calibration(25))
        self.assertIn('RT SRC IN_T 50',channel.calibration(50))
        self.assertIn('RLT OUT_T 0 100',channel.calibration(100))

    def test_analytic_witness_has_correct_dc_gain_and_reflection_arrivals(self):
        t=np.linspace(0,12e-9,12001)
        for load in [25,50,100]:
            source=np.full(len(t),.2)
            expected=.2*load/((50 if load==50 else 10)+load)
            self.assertTrue(np.allclose(channel.analytic_line(t,source,load),expected,rtol=0,atol=1e-14))
        source=np.where(t<1e-9,.2,.6);w=channel.analytic_line(t,source,100)
        dc=.2*100/110;first=.4*(50/60)*(4/3)
        self.assertAlmostEqual(float(np.interp(2e-9,t,w)),dc,places=12)
        self.assertAlmostEqual(float(np.interp(3e-9,t,w)),dc+first,places=12)
        self.assertAlmostEqual(float(np.interp(5e-9,t,w)),dc+first*(1-2/9),places=12)


if __name__=='__main__':unittest.main()
