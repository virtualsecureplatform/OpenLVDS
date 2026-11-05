# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import parallel_post_mux_roots_v116 as c


class ParallelPostMuxRootsTests(unittest.TestCase):
    def bank(self):
        tg='.subckt '+c.TG+' A Z EN ENB VPWR VGND\nXn Z EN A VGND sky130_fd_pr__nfet_01v8 w=1.68 l=.15\n.ends\n'
        rows=[f'Xswitch1_0_{k} tree0_{k} selected en1_{k} en_b1_{k} VPWR VGND '+c.TG for k in range(4)]
        return tg+'.subckt '+c.base.name('w126')+' IN OUT VPWR VGND\n'+'\n'.join(rows)+'\n.ends '+c.base.name('w126')+'\n'

    def test_projection_preserves_complete_parent_bytes_and_original_root_controls(self):
        original=self.bank();bank=c.strengthen(original,c.base.name('w126'),c.name('w126'))
        self.assertEqual(c.projection(bank,'w126'),original)
        defs=c.source.native.definitions(bank)
        for k in range(4):
            rows=defs[c.name('w126')][1]
            a=next(w for w in rows if w[0]==f'Xswitch1_0_{k}')
            b=next(w for w in rows if w[0]==f'Xroot_parallel{k}')
            self.assertEqual(a[1:],b[1:])

    def test_rejects_old_branch_inverter_net_wrong_control_and_duplicate_roots(self):
        for text in [self.bank().replace('tree0_0','regenerated0'),
                     self.bank().replace('en1_0','en1_1'),
                     self.bank().replace('.ends '+c.base.name('w126'),
                         'Xswitch1_0_0 tree0_0 selected en1_0 en_b1_0 VPWR VGND '+c.TG+'\n.ends '+c.base.name('w126'))]:
            with self.assertRaises(ValueError):c.strengthen(text,c.base.name('w126'),c.name('w126'))
        bank=c.strengthen(self.bank(),c.base.name('w126'),c.name('w126'))
        with self.assertRaisesRegex(ValueError,'already'):c.strengthen(bank,c.name('w126'),'other')
        with self.assertRaisesRegex(ValueError,'rewired'):
            c.projection(bank.replace('Xroot_parallel0 tree0_0','Xroot_parallel0 tree0_1'),'w126')


if __name__=='__main__':unittest.main()
