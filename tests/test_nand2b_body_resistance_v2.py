# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_nand2b_body_resistance_v2 as analysis


class BodyResistanceTests(unittest.TestCase):
    def test_bound_uses_actual_body_and_correct_rail_with_parallel_paths(self):
        text=('.subckt cell A Y VGND VPWR\nR0 body mid 100\nR1 mid VGND 50\nR2 body VGND 300\n'
              'R3 pbody VPWR 20\nX0 Y A VGND body sky130_fd_pr__nfet_01v8 w=.65 l=.15\n'
              'X1 Y A VPWR pbody sky130_fd_pr__pfet_01v8 w=1 l=.15\n.ends\n')
        r=analysis.paths(text)
        self.assertEqual(r['maximum_by_rail_ohm'],dict(VGND=150,VPWR=20))
        self.assertEqual(r['devices'][0]['body'],'body')
        shorter=text.replace('R2 body VGND 300','R2 body VGND 30')
        self.assertEqual(analysis.paths(shorter)['maximum_by_rail_ohm']['VGND'],30)

    def test_floating_body_and_invalid_resistance_cannot_be_hidden(self):
        text=('.subckt cell A Y VGND VPWR\nR0 body other 10\n'
              'X0 Y A VGND body sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n')
        with self.assertRaisesRegex(ValueError,'not connected'):analysis.paths(text)
        with self.assertRaisesRegex(ValueError,'positive'):analysis.paths(text.replace('other 10','VGND -1'))
        self.assertEqual(analysis.paths(text.replace('other 10','VGND 10'))['maximum_by_rail_ohm'],dict(VGND=10,VPWR=None))


if __name__=='__main__':unittest.main()
