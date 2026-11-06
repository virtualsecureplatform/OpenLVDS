# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_shared_counter_v200 import terminal_peak


class CounterStressDiagnosis(unittest.TestCase):
    def test_all_pairs_include_hidden_body_excursion_and_exact_sample(self):
        values=[np.array([0.,.1,.2]),np.array([1.8,1.8,1.8]),np.zeros(3),np.array([0.,-.16,0.])]
        peak,sample,a,b=terminal_peak(values)
        self.assertAlmostEqual(peak,1.96);self.assertEqual((sample,a,b),(1,1,3))

    def test_nonfinite_samples_refused(self):
        with self.assertRaises(ValueError):terminal_peak([np.array([0.,np.nan]),*[np.zeros(2) for _ in range(3)]])


if __name__=='__main__':unittest.main()
