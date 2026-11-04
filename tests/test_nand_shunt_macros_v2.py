# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nand_shunt_macros_v3 as physical


class ShuntedNativeNandTests(unittest.TestCase):
    def test_extended_native_source_preserves_bulk_mapping_and_real_shunt_dimensions(self):
        for short,size in [('nand2_2',2),('nand2_8',4)]:
            model='sky130_fd_sc_hd__'+short
            lib=f'.subckt {model} A B VGND VNB VPB VPWR Y\nX0 Y A a_27_47# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends {model}\n'
            lib+=f'.subckt {physical.TAP} VGND VPWR\n.ends {physical.TAP}\n'
            text=physical.source(short,lib,'a_27_47#')
            self.assertIn('Xgate A B VGND VGND VPWR VPWR Y MID '+model,text)
            self.assertIn('X0 Y A MID VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15',text)
            self.assertIn(f'XCMID MID VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}',text)
            self.assertIn('XCY Y VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)
            self.assertEqual(text.count('Xtap_'),2)

    def test_revised_access_meets_the_observed_enclosure_and_mim_clearance_rules(self):
        p=physical.plan()
        self.assertGreaterEqual((p['mid_contact_width']-.17)/2,.06)
        self.assertGreaterEqual(.55-p['mid_contact_width']/2-.24,.14)
        self.assertGreaterEqual(p['mid_center'][1]-2-(p['power_y']+.3),1.34)
        self.assertGreaterEqual(p['mid_escape_y']-.3-(p['mid_center'][1]+2),1.34)
        self.assertLess(p['ground_y'],0)


if __name__=='__main__':unittest.main()
