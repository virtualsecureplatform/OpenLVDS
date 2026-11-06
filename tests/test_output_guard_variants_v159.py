# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import output_guard_variants_v159 as p


class OutputGuardCardsTests(unittest.TestCase):
    def fixture(self):
        return ('.subckt bank IN OUT VPWR VGND\n'
                'Xn OUT IN VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15 ad=.1 as=.1 pd=1 ps=1\n'
                'Xp OUT IN VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15\n'
                'R0 OUT o0 .12\nR1 OUT o1 .13\nC0 o0 VGND .1f $ **FLOATING\n'
                'Xo0 o0 VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n'
                'Xo1 o1 VGND sky130_fd_pr__cap_mim_m3_1\n+ w=2 l=2\n'
                'Xfine fine_b0 VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends bank\n')
    def labels(self):return dict(o0='OUT',o1='OUT',VGND='VGND',fine_b0='fine_b0')

    def test_only_intended_guards_change_with_other_native_and_passive_bytes_intact(self):
        text=self.fixture();original=text
        for keep in (0,1):
            candidate,proof=p.variant(text,'bank',self.labels(),keep)
            self.assertEqual(proof['original_native_mos'],2);self.assertEqual(proof['original_native_mims'],3)
            self.assertEqual(proof['candidate_native_mims'],1+keep)
            self.assertEqual(proof['retained_output_guards'],['Xo0'] if keep else [])
            self.assertIn('Xfine fine_b0 VGND',candidate);self.assertEqual(p.cards.passive_lines(text),p.cards.passive_lines(candidate))
            self.assertTrue(proof['all_original_mos_and_other_native_cards_byte_identical']);self.assertFalse(proof['candidate_layout_qualified'])
            for name in ('Xn','Xp','Xfine'):
                a,b=p.cards.records(text)[name];c,d=p.cards.records(candidate)[name];self.assertEqual(text[a:b],candidate[c:d])
        self.assertEqual(text,original)

    def test_wrong_geometry_alias_or_guard_count_is_refused(self):
        for keep in (-1,2,True):
            with self.assertRaises(ValueError):p.variant(self.fixture(),'bank',self.labels(),keep)
        for text,labels in [(self.fixture().replace('w=2 l=2','w=3 l=2',1),self.labels()),
                            (self.fixture(),dict(self.labels(),o1='selected')),
                            (self.fixture().replace('.subckt bank','.subckt other'),self.labels())]:
            with self.assertRaises(ValueError):p.variant(text,'bank',labels,1)


if __name__=='__main__':unittest.main()
