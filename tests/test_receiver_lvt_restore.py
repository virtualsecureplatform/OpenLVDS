# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from receiver_lvt_restore_experiment import source_variant, lower_first_nfet
from receiver_unclamped_restore_experiment import source_variant as previous_source
from layout import circuits, flatten


class LvtRestoration(unittest.TestCase):
    def test_only_first_restoration_nfet_model_changes(self):
        source = (Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text()
        before = previous_source(source)
        after = source_variant(source)
        old_ports, old = flatten(circuits(before), 'openlvds_receiver_core')
        new_ports, new = flatten(circuits(after), 'openlvds_receiver_core')
        self.assertEqual(old_ports, new_ports)
        self.assertEqual(len(old), len(new))
        differences = []
        for a, b in zip(old, new):
            if a != b:
                self.assertEqual(a['nodes'], b['nodes'])
                self.assertEqual(a['params'], b['params'])
                self.assertEqual(a['name'], b['name'])
                self.assertEqual(a['model'], 'sky130_fd_pr__nfet_01v8')
                self.assertEqual(b['model'], 'sky130_fd_pr__nfet_01v8_lvt')
                differences.append(b)
        self.assertEqual(len(differences), 1)
        self.assertTrue(differences[0]['name'].endswith('__XIB0__XN_F0'))
        for name, definition in circuits(before).items():
            if name != 'openlvds_receiver_core':
                self.assertEqual(circuits(after)[name], definition)
        self.assertEqual(source_variant(source, False), previous_source(source, False))

    def test_already_modified_source_is_rejected(self):
        source = (Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text()
        with self.assertRaises(ValueError):
            lower_first_nfet(source_variant(source))

    def test_static_intervention_is_the_same_lvt_source_variant(self):
        from receiver_lvt_static import intervention
        from receiver_fast_restore_experiment import source_variant as clamped_source
        source = (Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text()
        self.assertEqual(intervention(clamped_source(source)), source_variant(source))


if __name__ == '__main__':
    unittest.main()
