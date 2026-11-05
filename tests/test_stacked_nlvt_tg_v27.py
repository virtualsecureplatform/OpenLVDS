# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_stacked_nlvt_tg_v27 as physical


class StackedTGChecks(unittest.TestCase):
    def test_native_schematic_and_swapped_drain_source_are_equivalent(self):
        source = physical.schematic()
        physical.native_check(source)
        physical.native_check(source.replace('XN A EN Z VGND', 'XN Z EN A VGND'))

    def test_wrong_control_body_flavor_and_junction_are_rejected(self):
        source = physical.schematic()
        for before, after in [(' ENB ', ' EN '), ('EN Z VGND', 'EN Z VPWR'),
                              (physical.N, 'sky130_fd_pr__nfet_01v8'),
                              ('ad=.4872', 'ad=.4871'), ('w=1.68', 'w=1.69')]:
            with self.subTest(fault=before), self.assertRaises(ValueError):
                physical.native_check(source.replace(before, after, 1))

    def test_wire_tally_follows_resistors_and_counts_coupling_at_both_ports(self):
        text = 'R1 A an 2\nR2 Z zn 3\nC1 an zn 2f\nC2 an 0 3f\nC3 zn VGND 4f\n'
        result = physical.wire_loading(text)
        self.assertAlmostEqual(result['wire_capacitance_upper_tally_ff']['A'], 5)
        self.assertAlmostEqual(result['wire_capacitance_upper_tally_ff']['Z'], 6)
        self.assertAlmostEqual(result['az_coupling_ff'], 2)
        self.assertTrue(result['excludes_native_mos_capacitance'])

    def test_shorted_public_ports_are_rejected(self):
        with self.assertRaises(ValueError):
            physical.wire_loading('R1 A Z 2\n')


if __name__ == '__main__':
    unittest.main()
