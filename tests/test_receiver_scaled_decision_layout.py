# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_scaled_decision_candidate as physical
from layout import circuits,flatten
from receiver_layout_reference import device_signature

ROOT=Path(__file__).resolve().parents[1]


class ScaledDecisionLayout(unittest.TestCase):
    def test_monitor_placement_keeps_exact_scaled_devices_and_functional_order(self):
        source=physical.clock.factory.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
        ports,devices=flatten(circuits(source),physical.TOP)
        placed=physical.reordered(devices,physical.place)
        self.assertEqual(len(ports),9);self.assertGreater(len(devices),70)
        self.assertEqual(device_signature(devices),device_signature(placed))
        self.assertEqual(placed[:-6],[d for d in devices if '__XTRACK__' not in d['name']])
        self.assertTrue(all('__XTRACK__' in d['name'] for d in placed[-6:]))
        self.assertEqual(physical.place(placed),placed)

    def test_incomplete_clock_evidence_cannot_trigger_cached_or_new_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);screen=root/'build/diagnostics/receiver_clamp/incomplete';screen.mkdir(parents=True)
            with patch.object(physical,'ROOT',root),patch.object(physical.clock,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all uniform-decision'):physical.source_gate(screen,root/'dc')
                run.assert_not_called()

    def test_failed_source_gate_cannot_draw_geometry(self):
        with patch.object(physical,'source_gate',side_effect=ValueError('clock failure')),patch.object(physical.physical,'build') as draw:
            with self.assertRaisesRegex(ValueError,'clock failure'):physical.build(ROOT/'source',ROOT/'static')
            draw.assert_not_called()


if __name__=='__main__':unittest.main()
