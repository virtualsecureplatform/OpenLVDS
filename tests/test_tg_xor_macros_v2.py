# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_tg_xor_macros_v2 as physical


class TgMacroSourceTests(unittest.TestCase):
    def test_only_real_pass_network_and_its_output_mim_are_retained(self):
        rows=[]
        for i,(data,en,enb) in enumerate([('b_iso','a_qb_iso','a_iso'),('b_qb_iso','a_iso','a_qb_iso'),('a_iso','b_qb_iso','b_iso'),('a_qb_iso','b_iso','b_qb_iso')]):
            rows += [f'Xtg_{i}_n xor_out {en} {data} VGND sky130_fd_pr__nfet_01v8 w=1 l=.15',f'Xtg_{i}_p xor_out {enb} {data} VPWR sky130_fd_pr__pfet_01v8 w=3 l=.15']
        rows+=['XOUTCAP99 xor_out VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2','Xignored x a y VGND sky130_fd_pr__nfet_01v8 w=99 l=.15']
        text,devices=physical.source('p3','\n'.join(rows));self.assertEqual(len(devices),9)
        self.assertNotIn('Xignored',text);self.assertNotIn('w=99',text);self.assertNotIn('VGND',text);self.assertNotIn('VPWR',text)
        self.assertEqual(text.count('w=3 l=.15'),4);self.assertEqual(text.count('w=1 l=.15'),4)

    def test_missing_real_device_or_output_shunt_is_rejected(self):
        with self.assertRaises(ValueError):physical.source('p3','Xtg_0_n xor_out a b VGND sky130_fd_pr__nfet_01v8 w=1 l=.15')


if __name__=='__main__':unittest.main()
