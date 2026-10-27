# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lvs_utils import clean_match,schematic_parameters

class LVSPolicy(unittest.TestCase):
    def test_unique_match_with_bad_properties_is_a_failure(self):
        self.assertTrue(clean_match('Final result: Circuits match uniquely.'))
        self.assertFalse(clean_match('Final result: Circuits match uniquely.\nProperty errors were found.'))
        self.assertFalse(clean_match('Netlists match uniquely with property errors.'))
    def test_fixed_width_is_checked_before_normalization(self):
        d=dict(model='sky130_fd_pr__res_high_po_0p35',params={'w':'.35','l':'10'})
        self.assertEqual(schematic_parameters(d),{'l':'10'})
        d['params']['w']='.5'
        with self.assertRaises(ValueError):schematic_parameters(d)

if __name__=='__main__':unittest.main()
