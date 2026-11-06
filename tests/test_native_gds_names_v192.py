# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_gds_names_v192 as p


class ExactGdsNameBijection(unittest.TestCase):
    def test_only_captured_directory_prefix_and_exact_complete_inventory_allowed(self):
        prefix='/work/OpenLVDS/build/diagnostics/counter/0123456789abcdef/top/'
        names=['top',prefix+'cap'];allowed={'top','cap'}
        self.assertEqual(p.canonical_names(names,prefix,allowed),{'top':'top',prefix+'cap':'cap'})
        for actual in (names+['cap'],['top','/other/cap'],['top',prefix+'../cap'],['top'],['top',prefix+'unknown']):
            with self.subTest(names=actual),self.assertRaises(ValueError):p.canonical_names(actual,prefix,allowed)
        with self.assertRaises(ValueError):p.canonical_names(names,'/other/',allowed)

    def test_mag_copy_changes_only_proved_use_names_and_preserves_ports_and_geometry(self):
        prefix='/work/OpenLVDS/build/diagnostics/counter/0123456789abcdef/top/'
        mapping={'top':'top',prefix+'cap':'cap'}
        before='magic\ntech sky130A\n<< metal4 >>\nrect 0 0 50 50\nuse '+prefix+'cap  cap_out\ntimestamp 0\ntransform 1 0 20 0 1 40\nbox 0 0 50 50\n<< labels >>\nrlabel metal4 1 1 1 1 0 CLK\nport 1 nsew\n<< end >>\n'
        after,n=p.mag_names(before,mapping);self.assertEqual(n,1)
        self.assertEqual(after,before.replace(prefix+'cap','cap',1))
        self.assertEqual(p.mag_names(after,mapping),(after,0))
        with self.assertRaises(ValueError):p.mag_names(before.replace(prefix+'cap','/other/cap'),mapping)


if __name__=='__main__':unittest.main()
