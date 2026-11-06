# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_unguarded_bank_chain_v170 as p


class BankChainGateTests(unittest.TestCase):
    def test_only_one_explicit_matching_artifact_is_accepted(self):
        line='/work/OpenLVDS/build/diagnostics/'+p.RC_CONTEXT+'/0123456789abcdef'
        self.assertEqual(p.artifact_from_log('noise\n'+line+'\n'+line+'\n',p.RC_CONTEXT),p.ROOT/'build/diagnostics'/p.RC_CONTEXT/'0123456789abcdef')
        self.assertIsNone(p.artifact_from_log(line+'suffix',p.RC_CONTEXT))
        with self.assertRaises(ValueError):p.artifact_from_log(line+'\n'+line.replace('0123456789abcdef','1111111111111111'),p.RC_CONTEXT)

    def test_wait_follows_one_verified_live_invocation_and_refuses_restart(self):
        info=dict(InvocationID='original',ActiveState='active',MainPID=str(os.getpid()))
        self.assertTrue(p.owner_live(info,'original'))
        with self.assertRaises(ValueError):p.owner_live(dict(info,InvocationID='replacement'),'original')
        self.assertFalse(p.owner_live(dict(info,ActiveState='failed'),'original'))
        with patch.object(p.os,'kill',side_effect=ProcessLookupError):self.assertFalse(p.owner_live(info,'original'))

    def test_passing_state_cannot_bypass_a_failed_electrical_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'state.json').write_text(json.dumps(dict(status='complete',passed=True,errors=0)))
            cases=[('rc',dict(joint_rc_passed=False)),('zero',dict(rows=[dict(error=None,result=dict(joint_rc_zero_screen_passed=False))])),
                   ('sparse',dict(comparison=dict(joint_rc_sparse_feasibility_passed=False)))]
            for stage,report in cases:
                (folder/'summary.json').write_text(json.dumps(report))
                with self.subTest(stage=stage),self.assertRaises(ValueError):p.require_result(folder,stage)
            (folder/'summary.json').write_text(json.dumps(dict(joint_rc_passed=True)))
            self.assertTrue(p.require_result(folder,'rc')['joint_rc_passed'])
            (folder/'state.json').write_text(json.dumps(dict(status='complete',passed=True,errors=1)))
            with self.assertRaises(ValueError):p.require_result(folder,'rc')


if __name__=='__main__':unittest.main()
