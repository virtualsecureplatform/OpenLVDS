# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import buffered_bank_model_v70 as p


class BufferedBankPrototypeTests(unittest.TestCase):
    def fixture(self):
        bank='.subckt bank IN OUT S0 VPWR VGND\nR1 IN OUT 10\nC1 OUT VGND 1f\n.ends bank\n'
        model=p.MODELS['buf1']
        cell='.subckt '+model+' A VGND VNB VPB VPWR X\n'+\
             'XN X A VGND VNB sky130_fd_pr__nfet_01v8 w=.52 l=.15\n'+\
             'XP X A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=.79 l=.15\n.ends '+model+'\n'
        return bank,cell

    def test_original_rc_bytes_stay_intact_and_load_moves_to_final_buffer(self):
        bank,cell=self.fixture();text=p.model(bank,cell,'buf1')
        self.assertTrue(text.startswith(bank))
        defs=p.native_source.native.definitions(text);ports,body=defs[p.NAME]
        self.assertEqual(ports,['IN','OUT','S0','VPWR','VGND'])
        self.assertEqual(body[0],['Xbank','IN','fine_raw','S0','VPWR','VGND','bank'])
        self.assertEqual(body[1],['Xoutput_buffer','fine_raw','VGND','VGND','VPWR','VPWR','OUT',p.MODELS['buf1']])

    def test_unknown_buffer_or_changed_native_bank_and_body_interface_is_rejected(self):
        bank,cell=self.fixture()
        with self.assertRaisesRegex(ValueError,'Unknown'):p.model(bank,cell,'other')
        with self.assertRaisesRegex(ValueError,'interface'):p.model(bank.replace('IN OUT','OUT IN'),cell,'buf1')
        with self.assertRaisesRegex(ValueError,'interface'):p.model(bank,cell.replace('A VGND VNB VPB VPWR X','A VGND VPB VNB VPWR X'),'buf1')
        with self.assertRaisesRegex(ValueError,'one actual'):p.model(bank+cell,cell,'buf1')


if __name__=='__main__':unittest.main()
