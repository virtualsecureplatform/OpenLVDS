# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_balanced_xnor_v2 as physical
import dcc_balanced_xnor_v2 as topology


class BalancedXnorMacroTests(unittest.TestCase):
    def test_mask_contact_mapping_and_schematic_both_swap_only_second_inputs(self):
        for copy in [0,1]:
            for pin in ['Y','VPWR','VGND','VPB','VNB']:self.assertEqual(topology.swapped_pin(copy,pin),pin)
        self.assertEqual([topology.swapped_pin(0,p) for p in ['A','B']],['A','B'])
        self.assertEqual([topology.swapped_pin(1,p) for p in ['A','B']],['B','A'])
        for copy,pin in [(2,'A'),(0,'CLK')]:
            with self.assertRaisesRegex(ValueError,'Unknown'):topology.swapped_pin(copy,pin)
        model=topology.MODEL
        library=f'.subckt {model} A B VGND VNB VPB VPWR Y\n.ends {model}\n'
        library+=f'.subckt {physical.TAP} VGND VPWR\n.ends {physical.TAP}\n'
        text=physical.source_schematic(model,library)
        self.assertIn('Xgate0 A B VGND VGND VPWR VPWR Y '+model,text)
        self.assertIn('Xgate1 B A VGND VGND VPWR VPWR Y '+model,text)
        self.assertEqual(text.count('Xtap_'),2)


if __name__=='__main__':unittest.main()
