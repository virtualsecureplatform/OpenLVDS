# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dcdl_bank_native_reference_v2 import definitions,reference


class NativeBankReferenceTests(unittest.TestCase):
    def test_local_macro_scope_and_native_units_are_preserved(self):
        sc='.subckt gate A Y V\nX0 Y A V V sky130_fd_pr__nfet_01v8 w=650000u l=150000u\n.ends\n'
        macro='.subckt gate A Y V\nX0 Y A V V sky130_fd_pr__pfet_01v8 w=1e+06u l=150000u\n.ends\n.subckt pair A Y V\nX0 A local V gate\nX1 local Y V gate\n.ends\n'
        rows=[(name,model,pin,net) for name,model,pins in [('a','gate',dict(A='I',Y='N',V='V')),('b','pair',dict(A='N',Y='O',V='V'))] for pin,net in pins.items()]
        text,counts=reference('top',['I','O','V'],rows,sc,{'pair':macro})
        self.assertEqual(counts,{'a':1,'b':2})
        self.assertEqual(text.count('sky130_fd_pr__pfet_01v8'),2)
        self.assertEqual(text.count('w=650000u l=150000u'),1)
        self.assertIn('__openlvds_bank_reference_internal__b__local',text)
        self.assertNotIn(' X0 ',text)

    def test_missing_model_or_disconnected_pin_is_rejected(self):
        for rows in [[('a','missing','A','I')],[('a','missing','A','')]]:
            with self.assertRaises(ValueError):reference('top',['I'],rows,'',{})

    def test_continuation_and_duplicate_definition_checks(self):
        text='.subckt cap A\n+ B\nX0 A B sky130_fd_pr__cap_mim_m3_1 w=2 l=3\n.ends\n'
        self.assertEqual(definitions(text)['cap'][0],['A','B'])
        with self.assertRaises(ValueError):definitions(text+text)

    def test_two_terminal_native_tie_resistor_remains_two_terminal(self):
        text='.subckt tie H L\nXR H L sky130_fd_pr__res_generic_po w=500000u l=500000u\n.ends\n'
        rows=[('tie','tie','H','V'),('tie','tie','L','G')]
        out,_=reference('top',['V','G'],rows,text,{})
        self.assertIn(' V G sky130_fd_pr__res_generic_po w=500000u l=500000u',out)


if __name__=='__main__':unittest.main()
