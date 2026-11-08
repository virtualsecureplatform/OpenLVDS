# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_counter_reassert_300 as p

class ReassertionDiagnosisTests(unittest.TestCase):
    def test_distinguishes_transition_glitch_from_settled_failure(self):
        t=np.arange(40001,dtype=float);v=np.zeros(len(t));v[32000:32050]=.3
        r=p.windows(t,{'stage':v})['nodes']['stage']
        self.assertFalse(r['original_new_checker']['below_original_180mv_limit'])
        self.assertTrue(r['legacy_relative_settled_window']['below_original_180mv_limit'])
        self.assertEqual(r['rising_50_percent_events_after_reassert_ps'],[])
    def test_preserves_real_logic_reassertion(self):
        t=np.arange(40001,dtype=float);v=np.zeros(len(t));v[32100:]=1.8
        r=p.windows(t,{'stage':v})['nodes']['stage']
        self.assertFalse(r['legacy_relative_settled_window']['below_original_180mv_limit'])
        self.assertEqual(len(r['rising_50_percent_events_after_reassert_ps']),1)
    def test_requires_full_finite_history(self):
        t=np.arange(26001,dtype=float)
        with self.assertRaises(ValueError):p.windows(t,{'stage':np.zeros(len(t))})
        t=np.arange(40001,dtype=float);v=np.zeros(len(t));v[32000]=np.nan
        with self.assertRaises(ValueError):p.windows(t,{'stage':v})
