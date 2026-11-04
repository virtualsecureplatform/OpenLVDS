# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_routed_bank_loading_v2 import loading


class RoutedBankLoadingTests(unittest.TestCase):
    def test_reports_coupling_once_and_keeps_intrinsic_mim_separate(self):
        text='.subckt bank IN OUT VGND VPWR\nR0 IN local 2\nC0 local VGND 5f\nC1 local OUT 3f\nC2 local IN 1f\nX0 OUT local VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\nXC local VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=3\n.ends\n'
        r=loading(text,dict(input='IN',output='OUT',ground='VGND'))
        self.assertAlmostEqual(r['input']['total_external_parasitic_capacitance_ff'],8)
        self.assertAlmostEqual(r['input']['intra_net_distributed_capacitance_ff'],1)
        self.assertEqual(r['input']['native_mos_terminal_counts'],dict(gate=1))
        self.assertEqual(r['input']['direct_native_mim_devices'][0]['width_um'],2)
        self.assertAlmostEqual(r['output']['external_parasitic_capacitance_ff']['input'],3)

    def test_ambiguous_anchors_and_negative_elements_are_rejected(self):
        text='.subckt bank A B\nC0 A B 1f\n.ends\n'
        with self.assertRaisesRegex(ValueError,'ambiguous'):loading(text,dict(node='A|B'))
        with self.assertRaisesRegex(ValueError,'Negative'):loading(text.replace('1f','-1f'),dict(node='A'))


if __name__=='__main__':unittest.main()
