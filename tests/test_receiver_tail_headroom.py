# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from receiver_tail_headroom_experiment import source_variant, reduce_decision_tail
from receiver_unclamped_restore_experiment import source_variant as previous_source
from layout import circuits


class ReceiverTailHeadroom(unittest.TestCase):
    def test_only_decision_tail_width_changes(self):
        source = (ROOT / 'analog/openlvds.spice').read_text()
        before, after = previous_source(source), source_variant(source)
        self.assertEqual(source_variant(source, False), before)
        old, new = circuits(before), circuits(after)
        self.assertEqual(old.keys(), new.keys())
        for name in old:
            if name != 'openlvds_receiver_core':
                self.assertEqual(old[name], new[name])
        ports, devices = old['openlvds_receiver_core']
        new_ports, new_devices = new['openlvds_receiver_core']
        self.assertEqual(ports, new_ports)
        self.assertEqual(len(devices), len(new_devices))
        differences = [(a, b) for a, b in zip(devices, new_devices) if a != b]
        self.assertEqual(len(differences), 1)
        a, b = differences[0]
        self.assertEqual(a[:3], b[:3])
        self.assertEqual(a[0], 'XCT')
        self.assertEqual(a[3], dict(w='64', l='0.5'))
        self.assertEqual(b[3], dict(w='16', l='0.5'))

    def test_changed_tail_and_clamped_topology_rejected(self):
        source = (ROOT / 'analog/openlvds.spice').read_text()
        with self.assertRaises(ValueError):
            reduce_decision_tail(source_variant(source))
        with self.assertRaises(ValueError):
            reduce_decision_tail(previous_source(source).replace('XCT CT NBC', 'XCT CT NB'))
        from receiver_fast_restore_experiment import source_variant as clamped_source
        with self.assertRaises(ValueError):
            reduce_decision_tail(clamped_source(source))

    def test_static_and_clock_interventions_match(self):
        from receiver_tail_headroom_static import intervention
        from receiver_fast_restore_experiment import source_variant as clamped_source
        source = (ROOT / 'analog/openlvds.spice').read_text()
        self.assertEqual(intervention(clamped_source(source)), source_variant(source))


if __name__ == '__main__':
    unittest.main()
