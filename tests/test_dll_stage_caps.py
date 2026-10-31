# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_dll_stage_caps import routing_caps,sections


class RoutingCapInspection(unittest.TestCase):
    def test_wire_cap_incidence_ignores_intra_net_capacitance_and_device_models(self):
        result=routing_caps('R0 a b 10\nR1 b c 5\nC0 a 0 2f\nC1 b other 3f\nC2 a c 99f\nX0 a 0 sky130_fd_pr__cap_mim_m3_1 w=30 l=30\n')
        for n in ['a','b','c']:self.assertAlmostEqual(result[n],5e-15)
        self.assertAlmostEqual(result['other'],3e-15)

    def test_long_extracted_wire_does_not_exhaust_python_recursion(self):
        rows=[f'R{i} n{i} n{i+1} 1' for i in range(10000)]+['C0 n10000 0 1f']
        result=routing_caps('\n'.join(rows));self.assertAlmostEqual(result['n0'],1e-15)

    def test_negative_capacitance_rejected(self):
        with self.assertRaisesRegex(ValueError,'Negative'):routing_caps('C0 a 0 -1f')

    def test_equal_capacitance_does_not_hide_disconnected_label_fragments(self):
        prefix='openlvds_dll_analog__XL__X0__N'
        with self.assertRaisesRegex(ValueError,'disconnected section net'):
            sections(f'C0 {prefix}.t0 0 1f\nC1 {prefix}.t1 0 1f')
