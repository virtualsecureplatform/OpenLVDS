# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nand2b_shunts_v2 as shunts


class Nand2bShuntSourceTests(unittest.TestCase):
    def test_both_private_nodes_are_guarded_without_resizing_native_transistors(self):
        library=('.subckt sky130_fd_sc_hd__nand2b_4 A_N B VGND VNB VPB VPWR Y\n'
                 'X0 a_27_47# A_N VGND VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n'
                 'X1 Y B a_215_47# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
                 '.subckt sky130_fd_sc_hd__tapvpwrvgnd_1 VGND VPWR\n.ends\n')
        for variant,(_,size) in shunts.VARIANTS.items():
            text,signals,mapping=shunts.source(variant,library)
            self.assertEqual(signals,['A_N','B','Y'])
            self.assertEqual(set(mapping),{'a_27_47#','a_215_47#'})
            self.assertEqual(text.count('w=.65 l=.15'),2)
            for mid in mapping.values():
                self.assertIn(f'XCAP_{mid} {mid} VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)
            self.assertIn(f'XCAP_OUT Y VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}',text)
            self.assertNotIn('.ic',text)


if __name__=='__main__':unittest.main()
