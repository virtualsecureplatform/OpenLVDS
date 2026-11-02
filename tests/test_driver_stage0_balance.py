# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driver_stage0_balance as balance
import probe_driver_stage0_balance as experiment
import probe_stronger_driver_shape as shape
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits


class FirstStageDriveBalance(unittest.TestCase):
    def source(self):
        return shape.shaped(transform(source_variant((shape.ROOT / 'analog/openlvds.spice').read_text()), shape.VARIANT))

    def test_only_two_first_stage_units_and_helper_binding_change(self):
        before = circuits(self.source())
        after = circuits(balance.transform(self.source()))
        self.assertEqual(set(after), (set(before) - {balance.OLD}) | {balance.NEW})
        for name, block in before.items():
            if name not in [balance.OLD, balance.taper.TOP]:
                self.assertEqual(block, after[name])
        old, new = [{r[0]: r for r in definitions[balance.taper.TOP][1]} for definitions in [before, after]]
        for name, row in old.items():
            if name == 'XLS':
                self.assertEqual(new[name], (row[0], row[1], balance.NEW, row[3]))
            else:
                self.assertEqual(row, new[name])
        old_rows = before[balance.OLD][1]
        rows = after[balance.NEW][1]
        self.assertEqual(len(rows), len(old_rows) + 2)
        for row in old_rows:
            self.assertIn(row, rows)
        for branch in [0, 1]:
            for stage, count in enumerate([2, 4, 8]):
                self.assertEqual(len([r for r in rows if r[0].startswith(f'XB{branch}_S{stage}_')]), count)

    def test_changed_capacitors_or_repeated_transformation_are_rejected(self):
        source = self.source()
        for bad in [source.replace('w=30 l=30', 'w=35 l=35'), balance.transform(source)]:
            with self.assertRaises(ValueError):
                balance.transform(bad)

    def test_measured_ss_failure_and_passing_ff_control_are_required(self):
        parent = experiment.ROOT / 'build/diagnostics/driver_shape_source/test'
        manifest = dict(tasks=[dict(id=n) for n in experiment.CASES])
        row = dict(metrics=dict(common_mode_pp_v=.149))
        with patch.object(experiment.stronger, 'check_variant'), \
                patch.object(experiment.stronger.pilot, 'bound', return_value=manifest), \
                patch.object(experiment.stronger.pilot, 'completed', return_value=(row, [])), \
                patch.object(Path, 'read_text', return_value='same circuit'):
            with self.assertRaisesRegex(ValueError, 'actual SS'):
                experiment.prepare(parent)
        with self.assertRaises(ValueError):
            experiment.run(Path('/tmp/other'))


if __name__ == '__main__':
    unittest.main()
