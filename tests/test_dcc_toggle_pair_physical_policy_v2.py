# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dcc_toggle_pair_physical_policy_v2 import interface_retained


class TogglePhysicalPolicyTests(unittest.TestCase):
    def source(self):return (Path(__file__).resolve().parents[1]/'sky130/v2/openlvds_dcc_toggle_pair_v2.v').read_text()

    def test_reset_qualified_both_loops_and_exact_combiner_are_required(self):
        source=self.source();self.assertTrue(interface_retained(source))
        for old,new in [('.B(reset_n)','.B(phase0)'),('.D(an)','.D(bn)'),('.A(a),.B(b)','.A(b),.B(a)'),
                        ('dfrtp_2','dfrtp_1'),('.Q(b)','.Q(a)'),('.X(an)','.X(phase0)'),('.RESET_B(reset_n)','.RESET_B(phase180)')]:
            self.assertFalse(interface_retained(source.replace(old,new,1)),(old,new))

    def test_only_power_connected_fill_tap_and_endcaps_may_be_added(self):
        source=self.source()
        for kind in ['fill_1','tapvpwrvgnd_1','decap_3']:
            self.assertTrue(interface_retained(source+f'\nsky130_fd_sc_hd__{kind} added (.VPWR(VPWR),.VGND(VGND),.VPB(VPWR),.VNB(VGND));'))
            self.assertFalse(interface_retained(source+f'\nsky130_fd_sc_hd__{kind} added (.A(phase0));'))
        self.assertFalse(interface_retained(source+'\nsky130_fd_sc_hd__buf_1 added (.A(phase0),.X(a));'))
        self.assertFalse(interface_retained(source.replace('.Q(a)', '.Q(a),.Q(b)',1)))
        self.assertFalse(interface_retained(source+'\nsky130_fd_sc_hd__decap_3 added (.VPWR(VGND));'))


if __name__=='__main__':unittest.main()
