# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_mim_bank_v2 as bank
import probe_dcdl_balanced_drive_v2 as measured


class PhysicalBankTopologyTests(unittest.TestCase):
    def test_every_legal_coarse_setting_matches_the_measured_128_cell_core(self):
        pins={'buf_4':['A','X'],'nand2_4':['A','B','Y'],'nand2_8':['A','B','Y'],'nand2b_4':['A_N','B','Y']}
        for coarse in range(16):
            source=measured.circuit(measured.parent_source.bank(measured.source_core.circuit(coarse,4)[0]),'core2')
            expected=Counter()
            for line in source.splitlines():
                words=line.split()
                if not words or not words[-1].startswith(bank.SC):continue
                nodes=words[1:-1];logical=[nodes[0],nodes[-1]] if words[-1].endswith('buf_4') else [nodes[0],nodes[1],nodes[-1]]
                expected[(words[-1],tuple(logical))]+=1
            actual=Counter()
            for c in bank.instances():
                if not c['name'].startswith(('input_buffer','output_buffer','forward','turn','pass','merge')):continue
                values=[]
                for pin in pins[c['model'].removeprefix(bank.SC)]:
                    n=c['pins'][pin]
                    if n.startswith('coarse'):n='VDD' if int(n[6:])<coarse else 'VSS'
                    n={'high':'VDD','low':'VSS'}.get(n,n);values.append(n)
                actual[(c['model'],tuple(values))]+=1
            self.assertEqual(sum(actual.values()),128)
            self.assertEqual(actual,expected,coarse)

    def test_real_control_drivers_and_exact_macro_count_without_duplicate_shunts(self):
        cells=bank.instances();counts=Counter(c['model'] for c in cells)
        self.assertEqual(len(cells),238)
        self.assertEqual(counts[bank.fine_unit.NAME],31);self.assertEqual(counts[bank.base_unit.NAME],1)
        self.assertEqual(counts[bank.SC+'inv_1'],31)
        self.assertEqual(counts[bank.SC+'buf_1'],31)
        for c in cells:
            if c['model']==bank.fine_unit.NAME:
                i=c['name'].removeprefix('fine_unit')
                self.assertEqual(c['pins'],dict(NODE='r0',EN='fine'+i,ENB='fine_b'+i,VDD='VPWR',VSS='VGND'))

    def test_checked_in_rtl_and_model_interfaces_match_the_generator(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/'sky130/v2'/f'{bank.name()}.v').read_text(),bank.verilog())
        self.assertEqual((root/'sky130/v2/dcdl_mim_blackboxes_v2.v').read_text(),bank.blackboxes())
        for coarse,fine in [(16,16),(32,32),(64,32),(128,32),(256,32)]:
            cells=bank.instances(coarse,fine)
            self.assertEqual(sum(c['model']==bank.fine_unit.NAME for c in cells),fine-1)
        with self.assertRaisesRegex(ValueError,'search dimensions'):bank.instances(8,32)
