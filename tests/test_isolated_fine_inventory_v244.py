# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolated_fine_bank_inventory_v244 as inventory

class NativeInventoryTests(unittest.TestCase):
    def source(self,mos=1479,mim=43,ports='A Y VPWR VGND',width='1'):
        return '\n'.join(['.subckt bank '+ports,
            *[f'Xn{k} Y A VGND VGND sky130_fd_pr__nfet_01v8 w={width} l=.15 ad=.1 as=.1 pd=1 ps=1' for k in range(mos)],
            *[f'Xc{k} Y VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2' for k in range(mim)],'.ends bank',''])

    def test_exact_isolated_bank_census_and_native_parameters(self):
        text=self.source();r=inventory.verify(text,'bank',text,'bank')
        self.assertEqual((r['native_mos'],r['native_mims']),(1479,43))
        self.assertTrue(r['native_parameters_preserved'])
        self.assertTrue(r['connectivity_requires_native_lvs'])
        self.assertFalse(r['qualified_phy'])

    def test_old_bank_census_or_lost_native_device_cannot_pass(self):
        reference=self.source()
        for mos,mim in [(1453,42),(1478,43),(1479,42),(1480,43),(1479,44)]:
            with self.subTest(mos=mos,mim=mim),self.assertRaisesRegex(ValueError,'census'):
                inventory.verify(reference,'bank',self.source(mos,mim),'bank')

    def test_same_census_does_not_hide_dimension_or_junction_changes(self):
        reference=self.source()
        for actual in [self.source(width='1.01'),reference.replace('ad=.1','ad=.2',1)]:
            with self.assertRaises(ValueError):inventory.verify(reference,'bank',actual,'bank')

    def test_public_port_permutation_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'public port order'):
            inventory.verify(self.source(),'bank',self.source(ports='Y A VPWR VGND'),'bank')

if __name__=='__main__':unittest.main()
