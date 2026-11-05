# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_dcdl_iterations_v3 import phase,abort_time_agrees


class FailureEpochTests(unittest.TestCase):
    def test_raw_abort_time_matches_printed_precision_without_accepting_another_epoch(self):
        log='Timestep too small; time = 8.98872e-09'
        self.assertTrue(abort_time_agrees(8.98871830810505e-9,log))
        self.assertFalse(abort_time_agrees(8.98870e-9,log))
        self.assertFalse(abort_time_agrees(9e-9,log))
        self.assertFalse(abort_time_agrees(float('nan'),log))

    def test_prefix_epoch_does_not_extend_to_active_or_complete_pulse_windows(self):
        self.assertEqual(phase(.654404e-9),'before-first-input-rise')
        self.assertEqual(phase(8.98872e-9),'after-first-input-fall-before-second-input-rise')
        for t in [0,2.1e-9,4e-9,6.1e-9,12.1e-9,16.1e-9,20e-9]:
            with self.subTest(time=t),self.assertRaises(ValueError):phase(t)


if __name__=='__main__':unittest.main()
