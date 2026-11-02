# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_stronger_driver_shape as pilot
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits


class StrongerShapedDriver(unittest.TestCase):
    def source(self, variant=pilot.VARIANT):
        return transform(source_variant((pilot.ROOT / 'analog/openlvds.spice').read_text()), variant)

    def test_completed_stronger_source_changes_only_the_two_existing_mim_sizes(self):
        before = circuits(self.source())
        after = circuits(pilot.shaped(self.source()))
        top = pilot.matrix.shape.pilot.circuit.TOP
        for name, block in before.items():
            if name != top:
                self.assertEqual(block, after[name])
        old, new = [{r[0]: r for r in definitions[top][1]} for definitions in [before, after]]
        self.assertEqual(old.keys(), new.keys())
        for name, row in old.items():
            if name in ['XCOUTP', 'XCOUTN']:
                self.assertEqual(new[name], (row[0], row[1], row[2], dict(w='30', l='30')))
            else:
                self.assertEqual(row, new[name])
        with self.assertRaises(ValueError):
            pilot.shaped(pilot.shaped(self.source()))
        with self.assertRaises(ValueError):
            pilot.shaped(self.source('taper_16_32_64'))

    def test_bounded_pilot_requires_both_polarities_at_tt25_and_ff0(self):
        tasks = pilot.tasks()
        self.assertEqual(len(tasks), 4)
        self.assertEqual({(t['process'], t['temperature'], t['op']) for t in tasks},
                         {(p, temp, op) for p, temp in [('tt', 25), ('ff', 0)]
                          for op in ['negative_op', 'positive_op']})

    def test_pilot_cannot_start_without_a_measured_common_mode_failure(self):
        failed = pilot.ROOT / 'build/diagnostics/driver_shape_source/fake'
        taper = pilot.ROOT / 'build/diagnostics/driver_gate_taper/fake'
        manifest = dict(tasks=[dict(id='ff_0_negative_op')])
        with patch.object(pilot, 'bound', return_value=manifest), patch.object(pilot, 'completed',
                return_value=(dict(metrics=dict(common_mode_pp_v=.149)), [])):
            with self.assertRaisesRegex(ValueError, 'measured FF0'):
                pilot.prepare(failed, taper)
        with self.assertRaises(ValueError):
            pilot.prepare(Path('/tmp/other'), taper)


if __name__ == '__main__':
    unittest.main()
