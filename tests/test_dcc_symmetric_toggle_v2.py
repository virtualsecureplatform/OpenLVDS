# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_toggle_pair_v4 as source


class SymmetricToggleTests(unittest.TestCase):
    def test_two_native_combiners_have_opposite_inputs_and_identical_output(self):
        library=''
        for name,ports,nodes in [
            ('dfrtp_1','CLK D RESET_B VGND VNB VPB VPWR Q','Q D CLK RESET_B'),
            ('and2b_1','A_N B VGND VNB VPB VPWR X','X A_N B VGND'),
            ('xnor2_2','A B VGND VNB VPB VPWR Y','Y A B VGND')]:
            library+=f'.subckt sky130_fd_sc_hd__{name} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.36 l=.15\n.ends sky130_fd_sc_hd__{name}\n'
        text=source.source_pair(1,library)
        self.assertIn('Xcombine0__X0 clock_out a b VGND',text)
        self.assertIn('Xcombine1__X0 clock_out b a VGND',text)
        self.assertIn('Xafeedback__X0 an a reset_n VGND',text)
        self.assertIn('Xbfeedback__X0 bn b reset_n VGND',text)
        self.assertEqual(len(source.native.terminals(text)),6)


if __name__=='__main__':unittest.main()
