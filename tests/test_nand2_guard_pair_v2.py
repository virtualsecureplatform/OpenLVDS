# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nand2_guard_pair_v2 as pair
import extract_nand2_guard_pair_v2 as extraction


class NAND2ShuntedPairTests(unittest.TestCase):
    def test_pair_preserves_native_mid_and_output_guards_and_maps_child_pins(self):
        text=f'''.subckt {pair.CHILD} Y B A VGND VPWR
Xn Y A MID VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15
Xcap MID VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2
Xout Y VGND sky130_fd_pr__cap_mim_m3_1 w=3 l=3
.ends {pair.CHILD}
'''
        result=pair.schematic(text)
        self.assertTrue(result.startswith(text))
        self.assertIn('.subckt '+pair.NAME+' A B Y VGND VPWR',result)
        for side in ['left','right']:
            self.assertIn('X'+side+' Y B A VGND VPWR '+pair.CHILD,result)
        self.assertEqual(result.count('w=2 l=2'),1)
        self.assertEqual(result.count('w=3 l=3'),1)
        for invalid in [text.replace(' Y B A VGND VPWR',' Y B A_N VGND VPWR'),text+text]:
            with self.assertRaises(ValueError):pair.schematic(invalid)

    def test_nand2_and_nand2b_physical_proofs_cannot_be_interchanged(self):
        root=Path('/fixture/build/diagnostics')
        self.assertIs(extraction.family(root/'nand2_guard_pair_physical_v2'/'id'),pair)
        with self.assertRaises(ValueError):
            extraction.family(root/'nand2b_guard_pair_physical_v2'/'id')
        self.assertEqual(pair.PORTS,['A','B','Y','VGND','VPWR'])
        self.assertNotIn('nand2b',pair.NAME)
