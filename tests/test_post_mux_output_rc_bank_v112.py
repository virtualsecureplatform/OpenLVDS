# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import post_mux_output_rc_bank_v112 as c


class MeasuredOutputSubstitutionTests(unittest.TestCase):
    def fixture(self):
        inv='.subckt '+c.base.INV+' A VGND VPWR Y\nXcore Y A VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\n.ends\n'
        bank=inv+'.subckt bank IN OUT VPWR VGND\nXuntouched IN fine_slow VPWR VGND other_cell\nXfine_driver fine_slow VGND VPWR OUT '+c.base.INV+'\nXfine_parallel fine_slow VGND VPWR OUT '+c.base.INV+'\n.ends bank\n'
        driver='.subckt '+c.DRIVER+' IN OUT VPWR VGND\nRwire IN n 1\nCwire n VGND 1f\nXnative OUT n VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\n.ends '+c.DRIVER+'\n'
        return bank,driver

    def test_replaces_only_final_pair_retains_distributed_driver_and_unrelated_calls(self):
        bank,driver=self.fixture();result=c.substitute(bank,'bank',driver)
        self.assertIn('Xuntouched IN fine_slow VPWR VGND other_cell\n',result)
        self.assertIn('Xfine_compound fine_slow OUT VPWR VGND '+c.DRIVER+'\n',result)
        self.assertNotIn('Xfine_parallel ',result);self.assertNotIn('Xfine_driver ',result)
        self.assertTrue(result.endswith(driver))
        self.assertEqual(c.cell_definition(result,c.base.INV),c.cell_definition(bank,c.base.INV))

    def test_rejects_swapped_supply_wrong_data_missing_or_duplicate_inverters(self):
        bank,driver=self.fixture()
        for broken in [bank.replace('fine_slow VGND VPWR OUT','fine_slow VPWR VGND OUT',1),
                       bank.replace('fine_slow VGND VPWR OUT','selected VGND VPWR OUT',1),
                       bank.replace('Xfine_parallel','Xmissing'),
                       bank.replace('.ends bank','Xfine_driver fine_slow VGND VPWR OUT '+c.base.INV+'\n.ends bank')]:
            with self.subTest(broken=broken):
                with self.assertRaisesRegex(ValueError,'exactly two'):c.substitute(broken,'bank',driver)
        with self.assertRaisesRegex(ValueError,'already present'):c.substitute(bank+driver,'bank',driver)


if __name__=='__main__':unittest.main()
