# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from simulate_link import parallel_stimulus


class ParallelStimulus(unittest.TestCase):
    def test_upstream_launch_matches_input_timing_constraint(self):
        launch=np.array([50.,52.6,55.0,57.55])
        words=[0,1,2,3]
        d0,d1=parallel_stimulus(launch,words,47.45)
        for points,shift in [(d0,0),(d1,1)]:
            points=np.array(points)
            for i,(at,word) in enumerate(zip(launch,words)):
                self.assertEqual(np.interp(at,points[:,0],points[:,1]),1.8*((word>>shift)&1))
                previous=47.45 if i==0 else launch[i-1]
                self.assertAlmostEqual(points[2*i+1,0],previous+.20)
                self.assertAlmostEqual(points[2*i+2,0],previous+.30)
                self.assertGreater(at-points[2*i+2,0],2.)

    def test_rejects_a_clock_period_too_short_for_the_interface(self):
        with self.assertRaisesRegex(ValueError,'setup'):
            parallel_stimulus([1.],[0],.8)


if __name__=='__main__':unittest.main()
