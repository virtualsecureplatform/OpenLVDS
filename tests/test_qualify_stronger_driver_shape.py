# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_stronger_driver_shape as qualification


class StrongerDriverSourceAdmission(unittest.TestCase):
    def test_scoped_analysis_uses_actual_stronger_counts_and_restores_helper(self):
        helper = qualification.matrix.shape.pilot
        with patch.object(helper, 'measure', return_value='measured') as original:
            with qualification.stronger_measurements():
                self.assertEqual(helper.measure(Path('/trace'), 'taper_16_32_64'), 'measured')
                original.assert_called_once_with(Path('/trace'), 'taper_16_64_128')
            self.assertIs(helper.measure, original)

    def test_analysis_restores_helper_after_unexpected_variant(self):
        helper = qualification.matrix.shape.pilot
        original = helper.measure
        with self.assertRaises(ValueError):
            with qualification.stronger_measurements():
                helper.measure(Path('/trace'), 'unknown')
        self.assertIs(helper.measure, original)

    def test_incomplete_pilot_never_dispatches_or_remeasures(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(qualification, 'ROOT', Path(tmp)):
            parent = Path(tmp) / 'build/diagnostics/stronger_driver_shape/test'
            parent.mkdir(parents=True)
            with patch.object(qualification.pilot, 'bound', return_value=dict(tasks=qualification.pilot.tasks())), \
                    patch.object(qualification.pilot, 'completed') as completed:
                with self.assertRaisesRegex(ValueError, 'Complete all four'):
                    qualification.prepare(parent)
                completed.assert_not_called()

    def test_first_taper_matrix_cannot_enter_stronger_analysis(self):
        with patch.object(qualification.pilot, 'bound', return_value=dict(identity=dict(variant='taper_16_32_64'))), \
                patch.object(qualification.matrix, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'declared stronger'):
                qualification.run(Path('/trace'))
            run.assert_not_called()

    def test_full_matrix_dispatch_is_two_workers_with_stronger_measurement(self):
        helper = qualification.matrix.shape.pilot
        with patch.object(qualification.pilot, 'bound', return_value=dict(identity=dict(variant='taper_16_64_128'))), \
                patch.object(helper, 'measure', return_value='result') as original, \
                patch.object(qualification.matrix, 'run', side_effect=lambda p, jobs:
                             helper.measure(p, 'taper_16_32_64')) as run:
            qualification.run(Path('/trace'))
            run.assert_called_once_with(Path('/trace'), jobs=2)
            original.assert_called_once_with(Path('/trace'), 'taper_16_64_128')
            self.assertIs(helper.measure, original)


if __name__ == '__main__':
    unittest.main()
