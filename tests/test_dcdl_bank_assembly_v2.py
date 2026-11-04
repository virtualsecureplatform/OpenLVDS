# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_dcdl_bank_inputs_v3 as assembly


class BankAssemblyTests(unittest.TestCase):
    def test_every_macro_is_placed_and_standard_cells_are_left_for_row_placement(self):
        cells=assembly.bank.instances();places=assembly.locations(cells)
        models=set(assembly.bank.COMPOUNDS.values())|{assembly.bank.native.fine_unit.NAME,assembly.bank.native.base_unit.NAME}
        self.assertEqual(set(places),{c['name'] for c in cells if c['model'] in models})
        self.assertEqual(len(places),96)
        self.assertTrue(all(p['orientation']=='N' for p in places.values()))
        self.assertEqual(places['merge0']['location'],[122,10])
        self.assertEqual(places['fine_unit30']['location'],[35,103])

    def test_overlap_and_die_violations_reject_the_whole_placement(self):
        boxes={'a':[1,1,4,4],'b':[4,1,8,4]}
        assembly.no_overlaps(boxes,[0,0,10,10])
        with self.assertRaisesRegex(ValueError,'overlap'):
            assembly.no_overlaps(dict(boxes,b=[3.99,1,8,4]),[0,0,10,10])
        with self.assertRaisesRegex(ValueError,'outside die'):
            assembly.no_overlaps(dict(boxes,b=[4,1,10.001,4]),[0,0,10,10])


if __name__=='__main__':unittest.main()
