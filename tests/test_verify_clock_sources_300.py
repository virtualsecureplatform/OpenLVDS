# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_clock_sources_300 as p

class VerifiedClockTests(unittest.TestCase):
    def clock(self,f=300,d=.5):
        period=1000/f
        return np.asarray([(k*period+offset,state) for k in range(20) for offset,state in ((0,1),(d*period,0))])
    def test_independent_frequency_duty_and_count(self):
        r=p.independent_metrics(self.clock(301,.51),p.policy.load()['requirements'])
        self.assertTrue(r['passed']);self.assertAlmostEqual(r['frequency_mhz'],301);self.assertAlmostEqual(r['duty_min'],.51)
        self.assertEqual(r['rising_edges'],20)
    def test_legacy_frequency_and_bad_duty_are_not_admitted(self):
        for clock in (self.clock(400),self.clock(300,.7)):
            self.assertFalse(p.independent_metrics(clock,p.policy.load()['requirements'])['passed'])
    def test_missing_duplicate_and_nonfinite_edges_are_rejected(self):
        good=self.clock()
        for bad in (np.delete(good,3,axis=0),np.vstack((good[0],good)),np.full_like(good,np.nan)):
            with self.assertRaises(ValueError):p.independent_metrics(bad,p.policy.load()['requirements'])
    def test_metrics_cannot_change_pass_flag_or_edge_count(self):
        r=p.independent_metrics(self.clock(),p.policy.load()['requirements'])
        for bad in (dict(r,passed=False),dict(r,rising_edges=19),dict(r,frequency_mhz=400)):
            with self.assertRaises(ValueError):p.compare_metrics(r,bad)
