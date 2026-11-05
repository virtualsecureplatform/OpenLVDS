# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerated_bank_v56 as p


class RegeneratedBankTests(unittest.TestCase):
    def fixture(self):
        cells='''.subckt inv A Y VGND VPWR
XN Y A VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15
XP Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15
XC Y VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2
.ends inv
.subckt tg A Z EN ENB VPWR VGND
XN A EN Z VGND sky130_fd_pr__nfet_01v8_lvt w=1.68 l=.15
XP Z ENB A VPWR sky130_fd_pr__pfet_01v8 w=3.36 l=.15
.ends tg
'''
        rows=['.subckt original IN OUT VPWR VGND','Xinput_inverse IN tap0 VGND VPWR inv']
        for k in range(4):
            rows += [f'Xswitch0_{k}_0 tap0 tree0_{k} VPWR VGND VPWR VGND tg',
                     f'Xswitch1_0_{k} tree0_{k} selected en{k} enb{k} VPWR VGND tg']
        rows += ['Xfine_driver selected OUT VGND VPWR inv','.ends original','']
        return cells,'\n'.join(rows)

    def test_changes_only_the_declared_inversion_boundaries(self):
        c,b=self.fixture();new=p.transform(c,b,'original','inv')
        self.assertNotIn('Xinput_inverse',new);self.assertNotIn(' tap0 ',new)
        for k in range(4):
            self.assertIn(f'Xgroup_inverse{k} tree0_{k} regenerated{k} VGND VPWR inv',new)
            self.assertIn(f'Xswitch1_0_{k} regenerated{k} selected',new)
        self.assertIn('Xfine_driver selected OUT VGND VPWR inv',new)
        before=p.primitive_counts(c+b,'original');after=p.primitive_counts(c+new,p.NAME)
        self.assertEqual(after['sky130_fd_pr__nfet_01v8_lvt']-before['sky130_fd_pr__nfet_01v8_lvt'],3)
        self.assertEqual(after['sky130_fd_pr__cap_mim_m3_1']-before['sky130_fd_pr__cap_mim_m3_1'],3)

    def test_both_clock_polarities_survive_every_root_selection(self):
        c,b=self.fixture();new=p.transform(c,b,'original','inv')
        def evaluate(text,top,clock,selected):
            body=p.native.definitions(text)[top][1];nets=dict(IN=clock,VPWR=1,VGND=0)
            nets.update({f'en{k}':int(k==selected) for k in range(4)});nets.update({f'enb{k}':int(k!=selected) for k in range(4)})
            for _ in range(20):
                for w in body:
                    if w[-1]=='inv' and w[1] in nets:nets[w[2]]=1-nets[w[1]]
                    elif w[-1]=='tg' and w[1] in nets and nets.get(w[3])==1 and nets.get(w[4])==0:nets[w[2]]=nets[w[1]]
            return nets['OUT']
        for selection in range(4):
            for clock in (0,1):self.assertEqual(evaluate(c+b,'original',clock,selection),evaluate(c+new,p.NAME,clock,selection))

    def test_missing_or_changed_original_branches_are_rejected(self):
        c,b=self.fixture()
        with self.assertRaises(ValueError):p.transform(c,b.replace('Xinput_inverse','Xother'),'original','inv')
        with self.assertRaises(ValueError):p.transform(c,b.replace('Xswitch1_0_3','Xother'),'original','inv')
        with self.assertRaises(ValueError):p.transform(c,b.replace('tree0_2 selected','IN selected'),'original','inv')
