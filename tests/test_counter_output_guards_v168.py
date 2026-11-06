# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import counter_output_guards_v168 as p


class CounterOutputGuardTests(unittest.TestCase):
    def fixture(self):
        return (f'.subckt {p.MODEL} A B Y VGND VPWR\n'
                'R0 Y y0 .1\nR1 Y y1 .2\nR2 VGND g0 .1\nR3 VGND g1 .2\n'
                'Xn Y A mid VGND sky130_fd_pr__nfet_01v8 w=1 l=.15 ad=.1\n'
                'X22 y0 g0 sky130_fd_pr__cap_mim_m3_1 l=1 w=1\n'
                'X25 y1 g1 sky130_fd_pr__cap_mim_m3_1\n+ l=1 w=1\n'
                'Xprivate mid VGND sky130_fd_pr__cap_mim_m3_1 l=1 w=1\n.ends\n'), (
                f'.subckt top A B Y VGND VPWR\nXlow0_set_pair A B Y VGND VPWR {p.MODEL}\n'
                f'Xlow1_set_pair A B Y VGND VPWR {p.MODEL}\n.ends\n')

    def test_only_output_guards_of_low0_are_resized(self):
        cells,module=self.fixture()
        for dimension in ('2','3'):
            library,pair,proof=p.libraries(cells,module,dimension)
            self.assertTrue(library.startswith(cells+'\n'))
            new=pair.splitlines()[1].split()[-1]
            _,body=p.native.definitions(library)[new]
            for w in body:
                if w[0] in ('X22','X25'):
                    self.assertEqual(dict(x.split('=') for x in w[-2:]),dict(w=dimension,l=dimension))
            self.assertIn('Xprivate mid VGND sky130_fd_pr__cap_mim_m3_1 l=1 w=1',library[len(cells):])
            self.assertEqual(pair.splitlines()[2],module.splitlines()[2])
            self.assertFalse(proof['candidate_layout_qualified']);self.assertEqual(proof['output_guards'],['X22','X25'])

    def test_wrong_geometry_connectivity_or_low0_selection_is_refused(self):
        cells,module=self.fixture()
        for c,m,d in [(cells.replace('X22 y0','X22 mid'),module,'2'),
                      (cells.replace('l=1 w=1','l=2 w=1',1),module,'2'),
                      (cells,module.replace('Xlow0_set_pair','Xother'),'2'),(cells,module,'4')]:
            with self.assertRaises(ValueError):p.libraries(c,m,d)


if __name__=='__main__':unittest.main()
