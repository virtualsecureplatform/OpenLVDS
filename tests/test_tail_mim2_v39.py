# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_tail_mim2_v39 as physical


class PhysicalTailMIMTests(unittest.TestCase):
    def test_exact_native_tail_mim(self):
        r=physical.native_check(physical.schematic())
        self.assertEqual(r['native_dimensions_um'],[2,2]);self.assertTrue(r['tail_to_ground_terminals_verified'])

    def test_wrong_dimensions_model_or_short_are_rejected(self):
        text=physical.schematic()
        for before,after in [('w=2','w=3'),('l=2','l=1'),('Xcap A VGND','Xcap A A'),('cap_mim_m3_1','cap_mim_m3_2')]:
            with self.subTest(fault=before),self.assertRaises(ValueError):physical.native_check(text.replace(before,after,1))

    def test_missing_ports_and_extra_devices_are_rejected(self):
        text=physical.schematic()
        with self.assertRaises(ValueError):physical.native_check(text.replace(' A VGND\n',' A VGND EXTRA\n',1))
        with self.assertRaises(ValueError):physical.native_check(text.replace('.ends','Xextra A VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends'))


if __name__=='__main__':unittest.main()
