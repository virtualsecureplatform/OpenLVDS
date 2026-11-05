# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_tg_quad_cell_v21 as cell


class NativePhysicalTGTests(unittest.TestCase):
    def test_both_full_native_devices_and_symmetric_junctions_are_required(self):
        source = cell.schematic()
        self.assertTrue(cell.native_check(source)['two_native_mos_preserved'])
        flipped = source.replace('XN A EN Z VGND', 'XN Z EN A VGND').replace('XP Z ENB A VPWR', 'XP A ENB Z VPWR')
        self.assertEqual(cell.native_check(source), cell.native_check(flipped))
        with self.assertRaises(ValueError):
            cell.native_check('\n'.join(line for line in source.splitlines() if not line.startswith('XN ')))

    def test_wrong_gate_body_or_junction_is_rejected_with_public_ports_intact(self):
        source = cell.schematic()
        for broken in (source.replace('XN A EN Z VGND', 'XN A ENB Z VGND'),
                       source.replace('XP Z ENB A VPWR', 'XP Z ENB A VGND'),
                       source.replace('ad=.4872', 'ad=.4871'),
                       source.replace('w=3.36', 'w=3.35')):
            with self.assertRaises(ValueError):
                cell.native_check(broken)


if __name__ == '__main__':
    unittest.main()
