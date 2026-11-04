# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_clock_cell_shunts_v2 as physical


class NativeClockShuntSourceTests(unittest.TestCase):
    def test_two_stack_nodes_have_separate_real_caps_and_preserved_native_bulk(self):
        lib='.subckt sky130_fd_sc_hd__nand3_2 A B C VGND VNB VPB VPWR Y\nX0 Y A a_27_47# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\nX1 a_27_47# B a_277_47# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\nX2 a_277_47# C VGND VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends sky130_fd_sc_hd__nand3_2\n'
        lib+='.subckt '+physical.TAP+' VGND VPWR\n.ends '+physical.TAP+'\n'
        text,signals,mapping=physical.source('nand3_2_o3',lib)
        self.assertEqual(signals,['A','B','C','Y']);self.assertEqual(len(mapping),2)
        self.assertEqual(text.count('w=.65 l=.15'),3)
        self.assertIn('Xgate A B C VGND VGND VPWR VPWR Y MID0 MID1 ',text)
        for mid in ['MID0','MID1']:self.assertIn(f'XCAP_{mid} {mid} VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)
        self.assertIn('XCAP_OUT Y VGND sky130_fd_pr__cap_mim_m3_1 w=3 l=3',text)

    def test_buffer_shunt_sizes_have_distinct_native_macro_names(self):
        self.assertNotEqual(physical.name('buf_8_o2'),physical.name('buf_8_o4'))
        with self.assertRaises(ValueError):physical.name('invented')


if __name__=='__main__':unittest.main()
