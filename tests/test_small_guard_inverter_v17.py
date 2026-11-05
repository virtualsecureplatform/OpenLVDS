# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_small_guard_inverter_v17 as design
import test_regular_clock_inverter_v11 as fixtures


class SmallerNativeGuardTests(unittest.TestCase):
    def test_only_the_one_guard_geometry_and_root_name_change_in_source(self):
        original = f'.subckt {design.OLD} A Y VGND VPWR\nXCAP Y VGND sky130_fd_pr__cap_mim_m3_1 w=4 l=4\n.ends {design.OLD}\n'
        changed = design.schematic(original)
        self.assertEqual(changed.replace(design.NAME, design.OLD).replace('w=3 l=3', 'w=4 l=4'), original)
        with self.assertRaises(ValueError):
            design.schematic(original.replace('w=4 l=4', 'w=2 l=4'))

    def test_all_mos_junctions_and_terminals_are_still_mandatory(self):
        original = fixtures.RegularInverterIsolationTests().flat()
        changed = original.replace('w=4 l=4', 'w=3 l=3')
        self.assertTrue(design.native_check(original, changed)['all_sixteen_mos_and_junctions_preserved'])
        for broken in (changed.replace('ad=.135', 'ad=.134', 1),
                       changed.replace('XP0 Y A VPWR VPWR', 'XP0 Y A VPWR VGND', 1),
                       changed.replace('w=3 l=3', 'w=3 l=4')):
            with self.assertRaises(ValueError):
                design.native_check(original, broken)


if __name__ == '__main__':
    unittest.main()
