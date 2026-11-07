# SPDX-License-Identifier: GPL-3.0-only
"""Do not hide clipped native transitions by matching another pulse's crossing."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_bank_latency_v348 as p


class BankLatencyTests(unittest.TestCase):
    def test_full_linear_rise_and_fall_slews(self):
        t=np.arange(0.,41.)
        v=np.interp(t,[0,5,15,25,35,40],[0,0,1.8,1.8,0,0])
        for up in (True,False):
            rows=p.edge_slews(t,v,up)
            self.assertEqual(len(rows),1)
            self.assertTrue(rows[0]['full_10_90_swing'])
            self.assertAlmostEqual(rows[0]['slew_ps'],8.)

    def test_clipped_first_pulse_cannot_borrow_next_pulses_high_crossing(self):
        t=np.arange(0.,81.)
        v=np.interp(t,[0,5,15,25,35,45,55,65,75,80],[0,0,1.5,1.5,0,0,1.8,1.8,0,0])
        for up in (True,False):
            rows=p.edge_slews(t,v,up)
            self.assertEqual(len(rows),2)
            self.assertFalse(rows[0]['full_10_90_swing'])
            self.assertIsNone(rows[0]['slew_ps'])
            self.assertTrue(rows[1]['full_10_90_swing'])
            self.assertAlmostEqual(rows[1]['slew_ps'],8.)

    def test_clipped_low_level_is_reported_for_both_polarities(self):
        t=np.arange(0.,41.)
        v=np.interp(t,[0,5,15,25,35,40],[.3,.3,1.8,1.8,.3,.3])
        for up in (True,False):
            row=p.edge_slews(t,v,up)[0]
            self.assertFalse(row['full_10_90_swing'])
            self.assertIsNone(row['slew_ps'])


if __name__=='__main__':unittest.main()
