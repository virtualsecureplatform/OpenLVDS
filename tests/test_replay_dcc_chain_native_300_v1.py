# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_dcc_chain_native_300_v1 as p


class CombinedReplayPreflightTests(unittest.TestCase):
    def test_pending_native_case_refused_without_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.four.VERSION))))
            with patch.object(p.four,'bound',side_effect=AssertionError('must not bind pending trace')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['0'])
                for cases in ([],['0','0'],['2'],['../0']):
                    with self.subTest(cases=cases),self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,cases)

    def test_unregistered_native_producer_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version='unknown'))))
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.run(parent,['0'])
