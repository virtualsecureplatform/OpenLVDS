# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from receiver_input_bias_experiment import source_variant, raise_input_bias, RESISTORS
from receiver_unclamped_restore_experiment import source_variant as previous_source
from layout import circuits, flatten


class ReceiverInputBias(unittest.TestCase):
    def test_only_four_input_ground_resistors_change(self):
        source = (ROOT / 'analog/openlvds.spice').read_text()
        before, after = previous_source(source), source_variant(source)
        self.assertEqual(source_variant(source, False), before)
        old_ports, old = flatten(circuits(before), 'openlvds_receiver_core')
        new_ports, new = flatten(circuits(after), 'openlvds_receiver_core')
        self.assertEqual(old_ports, new_ports)
        self.assertEqual(len(old), len(new))
        changed = []
        for a, b in zip(old, new):
            if a != b:
                self.assertEqual(a['name'], b['name'])
                self.assertEqual(a['nodes'], b['nodes'])
                self.assertEqual(a['model'], b['model'])
                self.assertEqual(a['params']['l'], '1.25')
                self.assertEqual(b['params'], dict(a['params'], l='2.5'))
                changed.append(a['name'])
        self.assertEqual(len(changed), 4)
        for name in RESISTORS:
            self.assertTrue(any(name in item for item in changed))
        for name, definition in circuits(before).items():
            if name != 'openlvds_receiver_core':
                self.assertEqual(circuits(after)[name], definition)

    def test_rejects_reapplication_and_wrong_topology(self):
        source = source_variant((ROOT / 'analog/openlvds.spice').read_text())
        with self.assertRaises(ValueError):
            raise_input_bias(source)
        source = previous_source((ROOT / 'analog/openlvds.spice').read_text())
        with self.assertRaises(ValueError):
            raise_input_bias(source.replace('XRLPPD PP PPRB', 'XRLPPD PN PPRB'))

    def test_static_and_clock_variants_match(self):
        from receiver_input_bias_static import intervention
        from receiver_fast_restore_experiment import source_variant as clamped_source
        source = (ROOT / 'analog/openlvds.spice').read_text()
        self.assertEqual(intervention(clamped_source(source)), source_variant(source))


if __name__ == '__main__':
    unittest.main()
