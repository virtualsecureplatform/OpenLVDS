# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_compact_candidate as compact


class CompactReceiverReplay(unittest.TestCase):
    def test_extra_physical_producers_are_captured_without_changing_frozen_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);code={'layout_receiver_compact_candidate.py':'hash','other_physical.py':'hash'}
            (root/'summary.json').write_text(json.dumps(dict(identity=dict(code=code))))
            previous=compact.replay.CODE
            def capture(parent,layout):
                self.assertTrue(set(previous)|set(code)|{'probe_receiver_compact_candidate.py'}<=set(compact.replay.CODE))
                return 'prepared'
            with patch.object(compact.replay,'prepare',side_effect=capture):
                self.assertEqual(compact.prepare(root,root),'prepared')
            self.assertIs(compact.replay.CODE,previous)
            with patch.object(compact.replay,'prepare',side_effect=ValueError('invalid physical proof')):
                with self.assertRaisesRegex(ValueError,'physical proof'):compact.prepare(root,root)
            self.assertIs(compact.replay.CODE,previous)

    def test_another_layout_cannot_be_mislabeled_compact(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'summary.json').write_text('{"identity":{"code":{}}}')
            with patch.object(compact.replay,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'compact placement'):compact.prepare(root,root)
            prepare.assert_not_called()
