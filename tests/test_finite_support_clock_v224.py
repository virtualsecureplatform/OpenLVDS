# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import math
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import finite_support_clock_v224 as p


class FiniteSupportClockPrecision(unittest.TestCase):
    def test_global_input_error_bound_includes_slew_renormalization(self):
        q=p.parameters(100,8);self.assertLess(q['global_input_difference_bound_v'],1e-6)
        observed=0.
        for k in range(-12000,12001):
            time=k*.001*q['old_width_s'];original=.5+.5*math.tanh(time/q['old_width_s'])
            observed=max(observed,1.8*abs(p.step(time,0,q)-original))
        self.assertLessEqual(16*observed,q['global_input_difference_bound_v'])
        self.assertFalse(q['qualified_phy'])
        for slew,cycles in ((0,8),(float('nan'),8),(100,9),(100,True)):
            with self.assertRaises(ValueError):p.parameters(slew,cycles)

    def test_exact_flat_levels_center_and_10_90_slew(self):
        q=p.parameters(100,8);w=q['width_s'];a=math.atanh(.8*q['tanh_limit'])*w
        for time in (-100*w,-9*w):self.assertEqual(p.step(time,0,q),0.)
        for time in (100*w,9*w):self.assertEqual(p.step(time,0,q),1.)
        self.assertEqual(p.step(0,0,q),.5);self.assertAlmostEqual(p.step(-a,0,q),.1);self.assertAlmostEqual(p.step(a,0,q),.9)
        self.assertAlmostEqual(2*a*1e12,100.)
        values=[p.step(k*w/100,0,q) for k in range(-1000,1001)]
        self.assertTrue(all(a<=b for a,b in zip(values,values[1:])))

    def test_every_pulse_uses_finite_support_guards(self):
        expr,q=p.expression(dict(input_slew_ps=100,cycles=8,frequency_mhz=410,duty=.6))
        self.assertEqual(expr.count('time<='),16);self.assertEqual(expr.count('time>='),16);self.assertEqual(expr.count('tanh('),16)
        self.assertLess(q['global_input_difference_bound_v'],1e-6)


if __name__=='__main__':unittest.main()
