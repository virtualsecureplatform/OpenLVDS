# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import mim_switch_2x3_v2 as old
import moscap_fine_bank_v88 as model


class NarrowedGateCapTests(unittest.TestCase):
    def fixture(self):
        top = model.original.name('w084')
        return (model.original.unit(old.schematic(), 'w084')+
                f'.subckt {top} NODE EN ENB VDD VSS\nX0 NODE EN ENB VDD VSS {top}_unit\n.ends {top}\n')

    def test_only_capacitor_width_and_top_identity_change(self):
        before = self.fixture()
        for profile, width in model.WIDTHS.items():
            after = model.rescale(before, profile)
            self.assertEqual(after.count('w='+width+' l=.15'), 2)
            for line in before.splitlines():
                if line.startswith('X') and not line.startswith(('Xgatecap_', 'X0 NODE EN ENB')):
                    self.assertIn(line, after)
            self.assertNotIn(model.original.name('w084'), after)
            self.assertIn('X0 NODE EN ENB VDD VSS '+model.name(profile)+'_unit', after)

    def test_changed_capacitor_pair_and_unknown_profile_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            model.rescale(self.fixture(), 'other')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            model.rescale(self.fixture().replace('Xgatecap_n ', 'Xmissing '), 'w080')


if __name__ == '__main__':
    unittest.main()
