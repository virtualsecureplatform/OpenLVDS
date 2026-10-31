# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pfd_fast_reset_policy import pfd_fast_reset_paths_retained
from pfd_qreset_policy import pfd_qreset_paths_retained

ROOT = Path(__file__).resolve().parents[1]


class PFDFastResetPolicy(unittest.TestCase):
    def source(self):
        return (ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text()

    def test_single_gate_reset_has_its_own_policy(self):
        self.assertTrue(pfd_fast_reset_paths_retained(self.source()))
        self.assertFalse(pfd_qreset_paths_retained(self.source()))
        self.assertFalse(pfd_fast_reset_paths_retained(
            (ROOT / 'sky130/experiments/lvds_pfd_area_qreset.v').read_text()))

    def test_wrong_reset_equation_or_buffer_feedback_is_rejected(self):
        source = self.source()
        for a, b in [('.A1(raw_up)', '.A1(UP)'), ('.B2(logic1)', '.B2(logic0)'),
                     ('.B1(disallow)', '.B1(PD_ENABLE)'), ('.Y(disallow)', '.Y(clear_b)'),
                     ('.RESET_B(clear_b)', '.RESET_B(disallow)')]:
            self.assertNotEqual(source.replace(a, b), source)
            with self.subTest(wiring=a):
                self.assertFalse(pfd_fast_reset_paths_retained(source.replace(a, b)))

    def test_clock_data_and_output_connections_are_preserved(self):
        source = self.source()
        for a, b in [('.CLK(FB)', '.CLK(UP)'), ('.D(logic1)', '.D(logic0)'),
                     ('.A(raw_dn),.X(DN)', '.A(raw_up),.X(DN)')]:
            self.assertFalse(pfd_fast_reset_paths_retained(source.replace(a, b)))
