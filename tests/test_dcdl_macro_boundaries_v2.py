# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from add_dcdl_macro_boundaries_v2 import boundary


class MacroBoundaryMetadataTests(unittest.TestCase):
    def test_native_lef_origin_is_preserved_on_the_gds_grid(self):
        lef='ORIGIN 0.190 0.300 ;\nSIZE 6.820 BY 3.600 ;\n'
        self.assertEqual(boundary(lef,.001),[-190,-300,6630,3300])
        lef='ORIGIN 0.000 -0.100 ;\nSIZE 12.400 BY 11.600 ;\n'
        self.assertEqual(boundary(lef,.001),[0,100,12400,11700])

    def test_ambiguous_or_off_grid_boundaries_are_rejected(self):
        for lef in ['SIZE 1 BY 1 ;','ORIGIN 0 0 ;\nSIZE 1.0004 BY 1 ;']:
            with self.assertRaises(ValueError):boundary(lef,.001)


if __name__=='__main__':unittest.main()
