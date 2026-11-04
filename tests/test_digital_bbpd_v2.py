# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_digital_bbpd_v2 as pd

class EdgeSamplerMeasurements(unittest.TestCase):
    def measure(self,a,b,swap=0,offset=20):
        t=np.arange(0,43)*1e-9
        wave=np.column_stack([t,np.ones(len(t))*a,np.ones(len(t))*b])
        spec=dict(reference_slew_ps=100,swap=swap,offset_ps=offset)
        with patch.object(pd.base,'read_raw',return_value=(['time','v(qa)','v(qb)'],wave)):
            return pd.measure(Path('/fixture'),spec)
    def test_swap_is_normalized_before_sign_voting(self):
        for a,b,swap in [(0,1.8,0),(1.8,0,1)]:
            r=self.measure(a,b,swap)
            self.assertEqual(r['correct_sign_fraction'],1)
            self.assertEqual(len(r['votes']),12)
            self.assertFalse(r['detector_admitted'])
    def test_dead_zone_and_unresolved_voltage_are_not_correct_sign(self):
        for a,b,ambiguous,unresolved in [(1.8,1.8,1,0),(.9,1.8,0,1)]:
            r=self.measure(a,b)
            self.assertEqual(r['correct_sign_fraction'],0)
            self.assertEqual(r['ambiguous_fraction'],ambiguous)
            self.assertEqual(r['unresolved_fraction'],unresolved)
    def test_opposite_sign_cannot_be_counted_as_an_early_event(self):
        self.assertEqual(self.measure(1.8,0)['correct_sign_fraction'],0)
        self.assertEqual(self.measure(1.8,0,offset=-20)['correct_sign_fraction'],1)
