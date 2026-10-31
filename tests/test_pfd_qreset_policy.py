# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pfd_qreset_policy import pfd_qreset_paths_retained
from physical_policy import pfd_area_paths_retained

ROOT = Path(__file__).resolve().parents[1]


class PFDQResetPolicy(unittest.TestCase):
    def source(self):
        return (ROOT / 'sky130/experiments/lvds_pfd_area_qreset.v').read_text()

    def test_reset_architectures_have_distinct_policies(self):
        previous = (ROOT / 'sky130/experiments/lvds_pfd_area.v').read_text()
        self.assertTrue(pfd_area_paths_retained(previous))
        self.assertFalse(pfd_qreset_paths_retained(previous))
        self.assertTrue(pfd_qreset_paths_retained(self.source()))
        self.assertFalse(pfd_area_paths_retained(self.source()))

    def test_retained_cells_do_not_excuse_wrong_clock_reset_or_output_wiring(self):
        source = self.source()
        for a, b in [('.CLK(REF)', '.CLK(FB)'),
                     ('.A(raw_up),.X(UP)', '.A(raw_dn),.X(UP)'),
                     ('.A_N(both)', '.A_N(raw_up)'),
                     ('coincidence(.A(raw_up),.B(raw_dn)', 'coincidence(.A(raw_up),.B(DN)'),
                     ('.A(RESET_N),.B(PD_ENABLE)', '.A(logic1),.B(PD_ENABLE)')]:
            self.assertNotEqual(source.replace(a, b), source)
            with self.subTest(wiring=a):
                self.assertFalse(pfd_qreset_paths_retained(source.replace(a, b)))

    def test_flip_flop_data_must_be_tied_to_a_high_constant(self):
        source = self.source()
        self.assertFalse(pfd_qreset_paths_retained(source.replace('.D(logic1)', '.D(logic0)')))
        self.assertFalse(pfd_qreset_paths_retained(source.replace('.D(logic1)', '.D(REF)')))

    def test_duplicate_coincidence_cell_is_rejected(self):
        source = self.source()
        extra = 'sky130_fd_sc_hd__and2_4 coincidence(.A(raw_up),.B(raw_dn),.X(other));\n'
        self.assertFalse(pfd_qreset_paths_retained(source + extra))
