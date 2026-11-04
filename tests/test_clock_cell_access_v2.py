# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_clock_cell_access_v2 as access


class NativeClockAccessTests(unittest.TestCase):
    def test_two_stack_nodes_become_distinct_ports_without_resizing(self):
        source='.subckt native A B C VGND VPWR Y\nX0 Y A a_27_47# VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\nX1 a_27_47# B a_277_47# VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\nX2 a_277_47# C VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends native\n'
        text,mapping=access.reference(source)
        self.assertEqual(len(set(mapping.values())),2);self.assertTrue(text.startswith('.subckt native A B C VGND VPWR Y MID0 MID1\n'))
        self.assertEqual(text.count('w=.65 l=.15'),3)
        self.assertNotIn('a_27_47#',text);self.assertNotIn('a_277_47#',text)

    def test_inverter_needs_no_private_port(self):
        source='.subckt inv A Y VGND VPWR\nX0 Y A VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends inv\n'
        text,mapping=access.reference(source);self.assertEqual(text,source);self.assertEqual(mapping,{})

    def test_multiple_labels_leave_all_native_masks_unchanged(self):
        mag='magic\n<< locali >>\nrect 0 0 40 40\nrect 100 0 120 20\n<< labels >>\nrlabel metal1 0 0 0 0 0 A\nport 1 nsew\n<< end >>\n'
        text,points=access.annotate(mag,{'a_27_47#':'MID0','a_277_47#':'MID1'})
        self.assertEqual(text.split('<< labels >>')[0],mag.split('<< labels >>')[0]);self.assertEqual(len(points),1)
        self.assertIn('0 MID0',text);self.assertIn('0 MID1',text);self.assertIn('port 3 nsew',text)


if __name__=='__main__':unittest.main()
