# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pfd_candidate_policy import pfd_candidate_paths_retained

ROOT = Path(__file__).resolve().parents[1]


class PFDCandidatePolicy(unittest.TestCase):
    def test_policy_label_must_match_the_actual_reset_topology(self):
        previous = (ROOT / 'sky130/experiments/lvds_pfd_area.v').read_text()
        fast = (ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text()
        self.assertTrue(pfd_candidate_paths_retained(previous, 'pulse-area'))
        self.assertFalse(pfd_candidate_paths_retained(previous, 'pulse-area-fast-reset'))
        self.assertTrue(pfd_candidate_paths_retained(fast, 'pulse-area-fast-reset'))
        self.assertFalse(pfd_candidate_paths_retained(fast, 'pulse-area'))

    def test_missing_unknown_and_unselected_q_only_policies_are_rejected(self):
        source = (ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text()
        for policy in [None, '', 'unknown', 'pulse-area-q-reset']:
            self.assertFalse(pfd_candidate_paths_retained(source, policy))

    def test_supported_label_cannot_excuse_wrong_clock_wiring(self):
        source = (ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text()
        self.assertFalse(pfd_candidate_paths_retained(source.replace('.CLK(FB)', '.CLK(REF)'),
                                                    'pulse-area-fast-reset'))
