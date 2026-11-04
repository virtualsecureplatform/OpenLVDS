# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_mim_switch_unit_v2 import port_wire_capacitance


class UnitWireLoadingTests(unittest.TestCase):
    def test_coupling_caps_count_at_both_resistively_connected_ports(self):
        text='R0 NODE n 10\nR1 EN e 20\nC0 n e 2f\nC1 n 0 3f\nC2 NODE n 100f\nXcap n VSS native_mim w=2 l=2\n'
        d=port_wire_capacitance(text,['NODE','EN','VSS'])
        self.assertAlmostEqual(d['NODE'],5e-15);self.assertAlmostEqual(d['EN'],2e-15)
        self.assertEqual(d['VSS'],0)
    def test_short_and_negative_capacitance_cannot_supply_a_loading_bound(self):
        for text in ['R0 NODE EN 1\n','C0 NODE EN -1f\n']:
            with self.assertRaises(ValueError):port_wire_capacitance(text,['NODE','EN'])
