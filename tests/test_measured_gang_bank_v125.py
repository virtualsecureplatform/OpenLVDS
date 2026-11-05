# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_gang_bank_v125 as c


class MeasuredBalancedGangTests(unittest.TestCase):
    def fixture(self):
        inv='.subckt '+c.INV+' A Y VPWR VGND\n.ends\n'
        rows=['Xfine_driver selected OUT VPWR VGND '+c.INV,'Xsentinel IN OUT leaf']
        rows += [f'Xgroup_inverse{k} tree0_{k} regenerated{k} VPWR VGND '+c.INV for k in range(4)]
        rows += ['Xfine_parallel selected OUT VPWR VGND '+c.INV,'Xleaf_parallel0_0 IN bus leaf']
        rows += [f'Xgroup_parallel{k} tree0_{k} regenerated{k} VPWR VGND '+c.INV for k in range(4)]
        parent=inv+'.subckt leaf A Z\n.ends\n.subckt '+c.base.name('b2')+' IN OUT VPWR VGND\n'+'\n'.join(rows)+'\n.ends '+c.base.name('b2')+'\n'
        driver='.subckt '+c.DRIVER+' IN OUT VPWR VGND\nRin IN gate 10\nCcouple gate OUT 1f\n.ends '+c.DRIVER+'\n'
        return parent,driver

    def test_five_measured_gangs_recover_parent_bytes_and_retain_extracted_coupling(self):
        parent,driver=self.fixture()
        result=c.rename(c.collapse_pairs(parent,c.base.name('b2'),driver),c.base.name('b2'),c.name('b2'))
        self.assertEqual(c.projection(result,'b2'),parent)
        self.assertTrue(result.endswith(driver))
        body=c.source.native.definitions(result)[c.name('b2')][1]
        self.assertEqual(sum(w[-1]==c.DRIVER for w in body),5)
        self.assertIn('Xsentinel IN OUT leaf\n',result)

    def test_rejects_wrong_data_supply_missing_gang_and_already_measured_bank(self):
        parent,driver=self.fixture()
        for broken in [parent.replace('Xgroup_inverse0 tree0_0','Xgroup_inverse0 tree0_1'),
                       parent.replace('Xfine_driver selected OUT VPWR VGND','Xfine_driver selected OUT VGND VPWR'),
                       parent.replace('Xfine_parallel selected OUT VPWR VGND '+c.INV+'\n','')]:
            with self.assertRaises(ValueError):c.collapse_pairs(broken,c.base.name('b2'),driver)
        with self.assertRaisesRegex(ValueError,'already'):c.collapse_pairs(parent+driver,c.base.name('b2'),driver)
        result=c.rename(c.collapse_pairs(parent,c.base.name('b2'),driver),c.base.name('b2'),c.name('b2'))
        with self.assertRaisesRegex(ValueError,'rewired'):
            c.projection(result.replace('Xfine_compound selected OUT','Xfine_compound IN OUT'),'b2')


if __name__=='__main__':unittest.main()
