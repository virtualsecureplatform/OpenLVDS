# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_unguarded_bank_followup_v176 as p


class NativeFollowupGates(unittest.TestCase):
    def test_wrong_bank_failed_chain_or_bad_handoff_cannot_prepare_followup(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            root=Path(directory);bank=root/'bank';artifact=root/'build/diagnostics'/p.chain.SPARSE_CONTEXT/'0123456789abcdef';artifact.mkdir(parents=True)
            rc=root/'rc';rc.mkdir();(rc/'manifest.json').write_text(json.dumps(dict(identity=dict(parent='bank'))))
            (artifact/'manifest.json').write_text(json.dumps(dict(identity=dict(parent='rc'))))
            state=dict(status='three_point_complete',artifacts=dict(sparse=str(artifact.relative_to(root))))
            with patch.object(p.chain,'require_result',return_value={}):
                self.assertEqual(p.source_artifact(state,bank),artifact)
                with self.assertRaises(ValueError):p.source_artifact(state,root/'other_bank')
                with self.assertRaises(ValueError):p.source_artifact(dict(state,status='failed'),bank)
                with self.assertRaises(ValueError):p.source_artifact(dict(state,artifacts=dict(sparse='../other')),bank)

    def test_complete_case_count_cannot_override_failed_native_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for kind,(_,_,count,gate) in p.RECIPES.items():
                (folder/'state.json').write_text(json.dumps(dict(status='complete',cases=count,errors=0)))
                (folder/'summary.json').write_text(json.dumps(dict(comparison={gate:False})))
                with self.subTest(kind=kind),self.assertRaises(ValueError):p.require_followup(folder,kind)
                (folder/'summary.json').write_text(json.dumps(dict(comparison={gate:True})))
                self.assertTrue(p.require_followup(folder,kind)['comparison'][gate])
                (folder/'state.json').write_text(json.dumps(dict(status='complete',cases=count-1,errors=0)))
                with self.assertRaises(ValueError):p.require_followup(folder,kind)


if __name__=='__main__':unittest.main()
