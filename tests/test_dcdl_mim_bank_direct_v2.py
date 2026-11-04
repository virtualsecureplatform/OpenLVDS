# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_mim_bank_direct_v2 as bank
import harden_dcdl_bank_direct_v2 as physical


class DirectBankTopologyTests(unittest.TestCase):
    def test_only_two_port_buffers_are_removed_and_every_other_device_is_retained(self):
        original=bank.base.instances();actual={c['name']:c for c in bank.instances()}
        self.assertEqual(len(original),174);self.assertEqual(len(actual),172)
        for c in original:
            if c['name'] in ['input_buffer','output_buffer']:self.assertNotIn(c['name'],actual);continue
            expected={p:{'f0':'IN','r0':'OUT'}.get(n,n) for p,n in c['pins'].items()}
            self.assertEqual(actual[c['name']],dict(c,pins=expected))
        self.assertEqual(sum(c['name'].startswith('fine_unit') for c in actual.values()),31)
        self.assertEqual(actual['shared_base']['pins']['NODE'],'OUT')

    def test_external_interface_and_generated_rtl_match_retained_model(self):
        text=bank.verilog()
        self.assertEqual(text.count('(* keep='),172)
        self.assertIn('module '+bank.name()+' (',text)
        self.assertIn('.Y(OUT)',text);self.assertIn('.B(IN)',text)
        self.assertNotIn(' input_buffer ',text);self.assertNotIn(' output_buffer ',text)
        self.assertEqual(bank.blackboxes(),bank.base.blackboxes())

    def test_final_connection_gate_requires_all_retained_cells_and_rejects_added_buffers(self):
        rows=[]
        for c in bank.instances():
            pins=dict(c['pins'])
            if c['model'].startswith(bank.native.SC):pins.update(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
            rows += [[c['name'],c['model'],p,n] for p,n in pins.items()]
        ports=['IN','OUT','VPWR','VGND',*bank.native.controls(16,32)]
        self.assertTrue(physical.connections_pass(rows,ports))
        self.assertFalse(physical.connections_pass([r for r in rows if r[0]!='fine_unit30'],ports))
        extra=[['unexpected',bank.native.SC+'buf_4','A','IN'],['unexpected',bank.native.SC+'buf_4','X','newnet']]
        self.assertFalse(physical.connections_pass(rows+extra,ports))


if __name__=='__main__':unittest.main()
