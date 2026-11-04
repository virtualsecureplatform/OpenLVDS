# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dcc_physical_policy_v3 import interface_retained


class ClonedTieTopologyTests(unittest.TestCase):
    def source(self):return (Path(__file__).resolve().parents[1]/'sky130/v2/openlvds_dcc_clock_hold_v2.v').read_text()

    def cloned(self):
        text=self.source().replace('sky130_fd_sc_hd__conb_1 tie(.HI(high),.LO(low));',
            'sky130_fd_sc_hd__conb_1 constant_a(.HI(high_a));\n    sky130_fd_sc_hd__conb_1 constant_b(.HI(high_b));')
        text=text.replace('.D(high),.RESET_B(areset)','.D(high_a),.RESET_B(areset)').replace('.D(high),.RESET_B(breset)','.D(high_b),.RESET_B(breset)')
        return text

    def test_original_and_two_true_constant_clones_preserve_the_same_clock_topology(self):
        self.assertTrue(interface_retained(self.source()));self.assertTrue(interface_retained(self.cloned()))
        self.assertTrue(interface_retained(self.cloned()+'\nsky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_0_Left_0();'))
        self.assertFalse(interface_retained(self.cloned()+'\nsky130_fd_sc_hd__decap_3 rogue(.Y(raw_q));'))

    def test_nonconstant_data_wrong_reset_feedback_and_hidden_drivers_are_rejected(self):
        text=self.cloned()
        for bad in [text.replace('.D(high_a)','.D(phase0)'),text.replace('.B(reset_n)','.B(high_a)',1),
            text+'\nsky130_fd_sc_hd__inv_1 rogue(.A(phase0),.Y(high_a));',text.replace('.A(raw_q)','.A(a)')]:
            self.assertFalse(interface_retained(bad))
