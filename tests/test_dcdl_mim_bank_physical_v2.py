# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_mim_bank_physical_v2 as physical


class CompoundBankViewTests(unittest.TestCase):
    def test_compound_boundaries_expand_to_the_exact_retained_native_gates(self):
        expected=Counter((c['model'],tuple(sorted(c['pins'].items()))) for c in physical.native.instances())
        reverse={v:k for k,v in physical.COMPOUNDS.items()};actual=Counter()
        for c in physical.instances():
            if c['model'] in reverse:
                pins={k:v for k,v in c['pins'].items() if k not in ['VPWR','VGND']}
                actual[(reverse[c['model']],tuple(sorted(pins.items())))]+=2
            else:actual[(c['model'],tuple(sorted(c['pins'].items())))]+=1
        self.assertEqual(actual,expected)
        self.assertEqual(len(physical.instances()),174)
        self.assertEqual(sum(c['model'] in reverse for c in physical.instances()),64)

    def test_generated_views_are_distinct_and_define_one_logical_output_per_pair(self):
        root=Path(__file__).resolve().parents[1]
        self.assertNotEqual(physical.name(),physical.native.name())
        self.assertEqual((root/'sky130/v2'/f'{physical.name()}.v').read_text(),physical.verilog())
        self.assertEqual((root/'sky130/v2/dcdl_mim_physical_blackboxes_v2.v').read_text(),physical.blackboxes())
        self.assertEqual(set(physical.COMPOUNDS),set(physical.SIGNALS))
