# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import uniform_tree_parasitic_isolation_v4 as isolation


class NativeParasiticIsolationTests(unittest.TestCase):
    MODEL = 'diagnostic_component'
    SOURCE = ('.subckt diagnostic_component A Y VDD VSS\n'
              'R1 A gate 1\nR2 body VSS 2\nR3 drain Y 3\nR4 rail VDD 4\n'
              'C1 gate drain 3f\nC2 drain VSS 5f\n'
              'XN drain gate VSS body sky130_fd_pr__nfet_01v8 w=0.42 l=0.15 ad=0.1218 pd=1.42 as=0.1218 ps=1.42\n'
              'XP rail gate drain rail sky130_fd_pr__pfet_01v8_hvt w=0.84 l=0.15 ad=0.2436 pd=2.26 as=0.2436 ps=2.26\n'
              'XMIM drain VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3\n'
              '.ends diagnostic_component\n')

    def test_native_junction_parameters_mim_and_body_connections_are_preserved(self):
        result, report = isolation.isolate(self.SOURCE, self.MODEL)
        self.assertIn('XN Y A VSS VSS sky130_fd_pr__nfet_01v8 w=0.42 l=0.15 ad=0.1218 pd=1.42 as=0.1218 ps=1.42', result)
        self.assertIn('XP VDD A Y VDD sky130_fd_pr__pfet_01v8_hvt w=0.84 l=0.15 ad=0.2436 pd=2.26 as=0.2436 ps=2.26', result)
        self.assertIn('XMIM Y VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3', result)
        self.assertNotIn('\nR', result); self.assertNotIn('\nC', result)
        self.assertEqual(report['removed_explicit_resistors'], 4)
        self.assertEqual(report['removed_explicit_parasitic_capacitors'], 2)
        self.assertEqual(report['retained_native_primitives'], 3)
        self.assertTrue(report['native_parameters_preserved'])
        self.assertFalse(report['qualified_phy'])
        self.assertFalse(report['electrical_qualification_passed'])

    def test_routing_short_between_public_ports_cannot_be_hidden(self):
        for extra in ('RSHORT gate drain 1\n', 'RSHORT VSS 0 1\n'):
            with self.assertRaises(ValueError):
                isolation.isolate(self.SOURCE.replace('C1 ', extra+'C1 '), self.MODEL)

    def test_negative_elements_sources_unknown_hierarchy_and_native_resistors_rejected(self):
        for broken in (self.SOURCE.replace('R1 A gate 1', 'R1 A gate -1'),
                       self.SOURCE.replace('C1 gate drain 3f', 'C1 gate drain -3f'),
                       self.SOURCE.replace('C1 gate drain 3f', 'B1 gate VSS V={0}'),
                       self.SOURCE.replace('XMIM drain VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3', 'XR drain VSS sky130_fd_pr__res_generic_m1 w=1 l=2'),
                       self.SOURCE.replace('XMIM drain VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3', 'XCHILD drain VSS other')):
            with self.assertRaises(ValueError):
                isolation.isolate(broken, self.MODEL)

    def test_transitive_wire_aliases_keep_unexposed_native_nodes(self):
        source = self.SOURCE.replace('R3 drain Y 3', 'R3 drain middle 3\nR5 middle Y 2')
        result, report = isolation.isolate(source, self.MODEL)
        self.assertEqual(report['wire_aliases']['drain'], 'Y')
        self.assertEqual(report['wire_aliases']['middle'], 'Y')
        self.assertIn('XN Y A VSS VSS', result)

    def test_actual_extractor_floating_cap_comments_are_parsed(self):
        source = self.SOURCE.replace('C1 gate drain 3f', 'C1 gate drain 3f $ **FLOATING')
        result, report = isolation.isolate(source, self.MODEL)
        self.assertEqual(report['removed_explicit_parasitic_capacitors'], 2)
        self.assertIn('XMIM Y VSS', result)


if __name__ == '__main__':
    unittest.main()
