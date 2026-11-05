# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import strong_coarse_bank_v122 as c


class StrongCoarseBankTests(unittest.TestCase):
    def fixture(self,profile):
        rows=[f'Xdelay{k} '+('IN' if k==1 else f'tap{k-1}')+f' tap{k} VPWR VGND '+c.BUFFER for k in range(1,16)]
        rows+=['Xtail_load tap15 unused_tail VPWR VGND '+c.BUFFER]
        bank='.subckt '+c.BUFFER+' A X VPWR VGND\n.ends\n.subckt '+c.base.name('w126')+' IN OUT VPWR VGND\n'+'\n'.join(rows)+'\n.ends '+c.base.name('w126')+'\n'
        driver='.subckt '+c.component_name(profile)+' IN OUT VPWR VGND\nRwire IN gate 1\n.ends '+c.component_name(profile)+'\n'
        return bank,driver

    def test_all_sixteen_buffers_project_exactly_without_changing_serial_chain_or_controls(self):
        for profile in c.PROFILES:
            original,rc=self.fixture(profile)
            result=c.rename(c.substitute(original,c.base.name('w126'),profile,rc),c.base.name('w126'),c.name(profile))
            self.assertEqual(c.projection(result,profile),original)
            body=c.source.native.definitions(result)[c.name(profile)][1]
            self.assertEqual(len(body),16)
            self.assertEqual(body[0][1:5],['IN','tap1','VPWR','VGND'])
            self.assertEqual(body[-1][1:5],['tap15','unused_tail','VPWR','VGND'])

    def test_wrong_input_body_missing_tail_and_duplicate_composition_are_rejected(self):
        original,rc=self.fixture('b2')
        for broken in [original.replace('Xdelay1 IN','Xdelay1 tap1'),
                       original.replace('tap2 VPWR VGND','tap2 VGND VPWR',1),
                       original.replace('Xtail_load tap15 unused_tail VPWR VGND '+c.BUFFER+'\n','')]:
            with self.assertRaises(ValueError):c.substitute(broken,c.base.name('w126'),'b2',rc)
        result=c.substitute(original,c.base.name('w126'),'b2',rc)
        with self.assertRaisesRegex(ValueError,'already'):c.substitute(result,c.base.name('w126'),'b2',rc)


if __name__=='__main__':unittest.main()
