# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tanh_voltage_pwl_v2 as source


class BoundedTanhPwlTests(unittest.TestCase):
    def test_full_two_pulse_source_preserves_midpoints_and_slew_and_meets_analytic_bound(self):
        points,cert=source.samples(100)
        self.assertEqual((points[0][0],points[-1][0]),(0,20000))
        self.assertLess(cert['maximum_interpolation_bound_v'],source.ERROR_LIMIT_V)
        self.assertLess(cert['maximum_slope_error_bound_v_per_ns'],.09)
        for a,b in zip(cert['midpoint_epochs_ps'],source.CENTERS_PS):self.assertAlmostEqual(a,b,places=8)
        for s in cert['slew_10_90_ps']:self.assertAlmostEqual(s,100,places=8)
        maximum=0.
        for (a,x),(b,y) in zip(points,points[1:]):
            for f in [.25,.5,.75]:
                maximum=max(maximum,abs(source.waveform(a+f*(b-a),100)-(x+f*(y-x))))
        self.assertLessEqual(maximum,cert['maximum_interpolation_bound_v'])
        self.assertTrue(all(v==0 for t,v in points if t<=1000))

    def test_underresolved_source_is_rejected_instead_of_relaxing_the_error_limit(self):
        with self.assertRaisesRegex(ValueError,'voltage-error bound'):source.samples(100,step_ps=2)
        for slew,step in [(0,.5),(float('nan'),.5),(100,0)]:
            with self.assertRaises(ValueError):source.samples(slew,step)


if __name__=='__main__':unittest.main()
