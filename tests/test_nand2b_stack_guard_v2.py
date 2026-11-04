# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nand2b_stack_guard_v2 as physical


class Nand2bStackGuardTests(unittest.TestCase):
    def test_only_stack_is_exposed_and_guarded_with_every_native_transistor_preserved(self):
        library=('.subckt sky130_fd_sc_hd__nand2b_4 A_N B VGND VNB VPB VPWR Y\n'
                 'X0 a_27_47# A_N VGND VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n'
                 'X1 Y a_27_47# a_215_47# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
                 '.subckt sky130_fd_sc_hd__tapvpwrvgnd_1 VGND VPWR\n.ends\n')
        for variant,(_,size) in physical.VARIANTS.items():
            text,signals,mapping=physical.source(variant,library)
            self.assertEqual(signals,['A_N','B','Y']);self.assertEqual(mapping,{'a_215_47#':'MID0'})
            self.assertIn('X0 a_27_47# A_N VGND VNB',text)
            self.assertIn('X1 Y a_27_47# MID0 VNB',text)
            self.assertEqual(text.count('w=.65 l=.15'),2)
            self.assertNotIn('MID1',text)
            self.assertEqual(text.count('sky130_fd_pr__cap_mim_m3_1'),2)
            self.assertIn('XCAP_MID0 MID0 VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)
            self.assertIn(f'XCAP_OUT Y VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}',text)


if __name__=='__main__':unittest.main()
