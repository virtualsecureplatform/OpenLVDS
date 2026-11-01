# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import receiver_operating_point_matrix as matrix


class OperatingPointMatrix(unittest.TestCase):
    def context(self, folder):
        (folder / 'manifest.json').write_text(json.dumps(dict(identity=dict(points=[{}] * 12))))

    def test_complete_evidence_is_analyzed_without_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); self.context(folder)
            for i in range(12): (folder / f'point_{i}.raw').write_bytes(b'evidence')
            with patch.object(matrix.probe, 'run') as run, patch.object(matrix.analysis, 'analyze', return_value='analysis') as analyze:
                self.assertEqual(matrix.run_case(folder, None), 'analysis')
                run.assert_not_called(); analyze.assert_called_once_with(folder)

    def test_partial_evidence_never_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); self.context(folder)
            raw = folder / 'point_0.raw'; raw.write_bytes(b'partial')
            with patch.object(matrix.probe, 'run') as run, patch.object(matrix.analysis, 'analyze') as analyze:
                with self.assertRaisesRegex(ValueError, 'Partial'): matrix.run_case(folder, 3)
                run.assert_not_called(); analyze.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'partial')

    def test_only_known_parser_error_can_continue_to_strict_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); self.context(folder)
            with patch.object(matrix.probe, 'run', side_effect=ValueError('Missing requested model/current operating-point vectors')) as run, patch.object(matrix.analysis, 'analyze', return_value='analysis') as analyze:
                self.assertEqual(matrix.run_case(folder, 3), 'analysis')
                run.assert_called_once_with(folder, 3); analyze.assert_called_once_with(folder)
            with patch.object(matrix.probe, 'run', side_effect=ValueError('Changed pinned runtime')), patch.object(matrix.analysis, 'analyze') as analyze:
                with self.assertRaisesRegex(ValueError, 'Changed pinned'): matrix.run_case(folder, None)
                analyze.assert_not_called()

    def test_incomplete_source_matrix_prevents_any_preparation(self):
        with patch.object(matrix.headroom, 'analyze', return_value=(Path('/unused'), dict(all_cases_observed=False))), patch.object(matrix.probe, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'all fifteen'): matrix.prepare(Path('/unused'))
            prepare.assert_not_called()


if __name__ == '__main__': unittest.main()
