# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_guarded_ff_access_v2 as access
import inspect_guarded_ff_access_v3 as updated


class GuardedFfAccessTests(unittest.TestCase):
    def test_polysilicon_anchor_is_labelled_on_native_poly_and_ambiguous_crossing_is_rejected(self):
        text=('magic\n<< poly >>\nrect 700 280 800 320\n<< locali >>\nrect 740 305 780 350\n'
              '<< labels >>\nrlabel metal1 0 0 0 0 0 CLK\nport 1 nsew\n<< end >>\n')
        result,_=updated.annotate(text,{'a_761_289#':'GUARD0'})
        self.assertIn('rlabel poly 763 291 763 291 0 GUARD0',result)
        self.assertEqual(result.split('<< labels >>')[0],text.split('<< labels >>')[0])
        ambiguous=text.replace('<< poly >>','<< ndiff >>\nrect 700 280 800 320\n<< poly >>')
        with self.assertRaisesRegex(ValueError,'ambiguous'):updated.annotate(ambiguous,{'a_761_289#':'GUARD0'})

    def test_labels_choose_actual_n_or_p_diffusion_without_changing_masks(self):
        text=('magic\n<< ndiff >>\nrect 100 40 180 90\n<< pdiff >>\nrect 300 400 380 450\n'
              '<< locali >>\nrect 100 40 180 90\nrect 300 400 380 450\n'
              '<< labels >>\nrlabel metal1 0 0 0 0 0 CLK\nport 1 nsew\n<< end >>\n')
        result,points=access.annotate(text,{'a_100_40#':'GUARD0','a_300_400#':'GUARD1'})
        self.assertIn('rlabel ndiff 102 42 102 42 0 GUARD0',result)
        self.assertIn('rlabel pdiff 302 402 302 402 0 GUARD1',result)
        self.assertEqual(result.split('<< labels >>')[0],text.split('<< labels >>')[0])
        self.assertEqual(len(points),2)
        with self.assertRaisesRegex(ValueError,'actual private diffusion'):
            access.annotate(text,{'a_900_900#':'GUARD0'})

    def test_only_actual_diagnosed_nodes_become_ports_and_transistors_are_preserved(self):
        source=('.subckt native CLK Q VNB\nX0 Q CLK a_100_40# VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n'
                'X1 a_300_400# CLK Q VNB sky130_fd_pr__pfet_01v8 w=1 l=.15\n.ends native\n')
        text,mapping=access.reference(source,['a_300_400#'])
        self.assertEqual(mapping,{'a_300_400#':'GUARD0'})
        self.assertIn('a_100_40#',text)
        self.assertIn('X1 GUARD0 CLK Q VNB sky130_fd_pr__pfet_01v8 w=1 l=.15',text)
        self.assertEqual(text.count('X0'),1);self.assertEqual(text.count('X1'),1)
        with self.assertRaisesRegex(ValueError,'actual native private'):access.reference(source,['a_900_900#'])


if __name__=='__main__':unittest.main()
