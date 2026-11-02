# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import matrix_receiver_tia_restore as matrix


class CachedReferencePreparation(unittest.TestCase):
    def reports(self,root):
        for v in matrix.pilot.control.VARIANTS:
            p=root/v;p.mkdir();(p/'summary.json').write_text('{}')

    def test_busy_completed_reference_is_retried_without_changing_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior=Path(tmp);self.reports(prior)
            with patch.object(matrix.pilot.control,'run',side_effect=[BlockingIOError(11,'busy'),'cached result']) as reader:
                with patch.object(matrix.pilot,'prepare',side_effect=lambda p,m:matrix.pilot.control.run(prior)):
                    self.assertEqual(matrix.prepare_child(Path('parent'),Path('matrix')),'cached result')
                self.assertIs(matrix.pilot.control.run,reader);self.assertEqual(reader.call_count,2)

    def test_incomplete_reference_cannot_request_scientific_reader(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(matrix.pilot.control,'run') as reader:
            with patch.object(matrix.pilot,'prepare',side_effect=lambda p,m:matrix.pilot.control.run(Path(tmp))):
                with self.assertRaisesRegex(ValueError,'Complete cached control'):matrix.prepare_child(Path('parent'),Path('matrix'))
            self.assertIs(matrix.pilot.control.run,reader);reader.assert_not_called()

    def test_scientific_error_is_preserved_and_reader_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior=Path(tmp);self.reports(prior)
            with patch.object(matrix.pilot.control,'run',side_effect=ValueError('scientific context changed')) as reader:
                with patch.object(matrix.pilot,'prepare',side_effect=lambda p,m:matrix.pilot.control.run(prior)):
                    with self.assertRaisesRegex(ValueError,'scientific context changed'):matrix.prepare_child(Path('parent'),Path('matrix'))
                self.assertIs(matrix.pilot.control.run,reader);self.assertEqual(reader.call_count,1)
