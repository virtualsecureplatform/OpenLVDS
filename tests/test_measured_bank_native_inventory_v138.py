# SPDX-License-Identifier: GPL-3.0-only
"""Admission guard tests; synthetic devices do not qualify a physical bank."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_bank_native_inventory_v138 as p


class MeasuredBankNativeInventoryTests(unittest.TestCase):
    def source(self,profile='b2',ports='IN OUT VPWR VGND'):
        count=1133+320*(int(profile[1])-1)
        rows=['.subckt bank '+ports]
        rows += [f'X{k} OUT IN VGND VGND sky130_fd_pr__nfet_01v8 w=0.65 l=0.15 ad=0.1 as=0.2 pd=1 ps=2' for k in range(count)]
        rows += [f'XC{k} OUT VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2' for k in range(42)]
        return '\n'.join(rows+['.ends bank',''])

    def test_both_exact_censuses_preserve_parameters_without_qualifying_connectivity(self):
        for profile,count in [('b2',1453),('b3',1773)]:
            source=self.source(profile);r=p.verify(source,'bank',source,'bank',profile)
            self.assertEqual((r['native_mos'],r['native_mims']),(count,42))
            self.assertTrue(r['native_parameters_preserved']);self.assertTrue(r['connectivity_requires_native_lvs'])
            self.assertFalse(r['joint_rc_extracted']);self.assertFalse(r['qualified_phy'])

    def test_missing_device_wrong_profile_and_changed_port_order_are_refused(self):
        source=self.source()
        missing='\n'.join(line for line in source.splitlines() if not line.startswith('X0 '))
        for actual,profile,reason in [(missing,'b2','census'),(source,'b3','census'),(self.source(ports='OUT IN VPWR VGND'),'b2','port order')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):p.verify(source,'bank',actual,'bank',profile)
        with self.assertRaisesRegex(ValueError,'profile'):p.verify(source,'bank',source,'bank','unknown')

    def test_same_census_does_not_hide_dimension_or_junction_changes(self):
        source=self.source()
        for changed,reason in [(source.replace('w=0.65','w=0.66',1),'dimensions'),(source.replace('ad=0.1','ad=0.11',1),'junction')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):p.verify(source,'bank',changed,'bank','b2')
        exchanged=source.replace('ad=0.1 as=0.2 pd=1 ps=2','ad=0.2 as=0.1 pd=2 ps=1')
        self.assertTrue(p.verify(source,'bank',exchanged,'bank','b2')['native_parameters_preserved'])


if __name__=='__main__':unittest.main()
