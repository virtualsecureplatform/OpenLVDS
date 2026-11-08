# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_tg2_four_bank_native_300_v1 as p


class ReplayPreflightTests(unittest.TestCase):
    def parent(self,folder,version=None):
        (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(version=version or p.four.VERSION))))
        return folder

    def test_pending_case_refused_before_expensive_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=self.parent(Path(tmp))
            with patch.object(p.four,'bound',side_effect=AssertionError('must not bind pending data')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['0'])

    def test_exact_registry_and_unique_explicit_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=self.parent(Path(tmp))
            self.assertIs(p.select(parent),p.four)
            for ids in ([],['0','0'],['2'],['../0']):
                with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,ids)
            self.parent(parent,'unregistered-producer')
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.select(parent)
