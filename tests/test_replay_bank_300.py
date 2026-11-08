# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic metrology checks, not analog circuit evidence."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_bank_300 as p
from regenerated_bank_periodic_measure_v67 import timing

class BankReplay300Tests(unittest.TestCase):
    def trace(self,f=310,duty=.6):
        t=np.arange(40001,dtype=float);period=1e6/f;pts=[(0,0)]
        for k in range(8):
            a=2000+k*period;b=a+duty*period
            pts.extend([(a,0),(a+200,1.8),(b,1.8),(b+200,0)])
        inp=np.interp(t,*zip(*pts));out=np.interp(t-750,t,inp)
        return t,inp,out,dict(cycles=8,frequency_mhz=f,duty=duty,coarse=0,fine=0)
    def test_full_timing_matches_original_with_correct_fast_quarter(self):
        for f in (290,300,310):
            for d in (.4,.5,.6):
                t,a,b,s=self.trace(f,d);r=p.independent_timing(t,a,b,s);original=timing(t,a,b,s)
                original['zero_code_fast_quarter_headroom_ps']=p.policy.budgets()['minimum_quarter_ps']-750
                original['zero_code_quarter_passed']=True
                self.assertTrue(all(p.same(v,original[k]) for k,v in r.items()))
                self.assertAlmostEqual(r['zero_code_fast_quarter_headroom_ps'],56.45161290322585)
    def test_missing_or_clipped_eighth_pulse_is_rejected(self):
        t,a,b,s=self.trace();b[t>24000]=0
        with self.assertRaises(ValueError):p.independent_timing(t,a,b,s)
        t,a,b,s=self.trace();b=np.minimum(b,1.5)
        with self.assertRaises(ValueError):p.independent_timing(t,a,b,s)
    def test_repeated_delay_error_preserved(self):
        t,a,b,s=self.trace();b=np.interp(t-800,t,a);b[t<10000]=np.interp(t-750,t,a)[t<10000]
        r=p.independent_timing(t,a,b,s)
        self.assertFalse(r['repeated_delay_screen_passed'])
        self.assertFalse(r['period_screen_passed'])
    def test_result_comparison_preserves_classifications(self):
        self.assertFalse(p.same({'passed':True},{'passed':False}))
        self.assertFalse(p.same([1.],[1.,2.]))
        self.assertFalse(p.same(float('nan'),float('nan')))
        self.assertTrue(p.same([1.],[1.+1e-8]))
