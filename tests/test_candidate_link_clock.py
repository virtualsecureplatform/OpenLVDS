# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from simulate_link import clocks


class CandidateClock(unittest.TestCase):
    def test_link_uses_characterized_phase_of_the_requested_bundle(self):
        args=SimpleNamespace(mhz=400,duty=.55,clock_source='ideal',jitter_pp_ps=0,
            dll_phase=True,bundle='candidate',process='tt',temperature=25)
        record=dict(quarter_phase_min_ps=610,quarter_phase_max_ps=630,clock_duty=.55,evidence_sha256='native proof')
        with patch('phy_candidate.phase',return_value=record) as phase:
            c0,c90,_,_,scope=clocks(args,50)
            phase.assert_called_once_with('candidate','tt',25,400,.55)
        self.assertAlmostEqual(c90[1][0]-c0[1][0],.620)
        self.assertIn('native proof',scope)
