# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_unguarded_bank_chain_v177 as p


class CollectedProducerTests(unittest.TestCase):
    def active(self):return dict(InvocationID='original',LoadState='loaded',ActiveState='active',MainPID=str(os.getpid()))
    def collected(self):return dict(InvocationID='',LoadState='not-found',ActiveState='inactive',MainPID='0')

    def test_collected_successful_service_keeps_matching_completed_artifact_eligible(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            root=Path(directory);bank=root/'build/diagnostics/bank/0123456789abcdef'
            rc=root/'build/diagnostics'/p.RC_CONTEXT/'1111111111111111';rc.mkdir(parents=True)
            (rc/'state.json').write_text(json.dumps(dict(status='complete',passed=True)))
            (rc/'summary.json').write_text(json.dumps(dict(joint_rc_passed=True)))
            (rc/'manifest.json').write_text(json.dumps(dict(identity=dict(parent=str(bank.relative_to(root))))))
            log=root/'producer.log';log.write_text('/work/OpenLVDS/'+str(rc.relative_to(root))+'\n')
            def execute(command,**kwargs):
                if command[-2]=='prepare':
                    kind='zero' if 'zero' in command[-3] else 'sparse'
                    context=p.ZERO_CONTEXT if kind=='zero' else p.SPARSE_CONTEXT
                    artifact=root/'build/diagnostics'/context/'2222222222222222';artifact.mkdir(parents=True)
                    (artifact/'state.json').write_text(json.dumps(dict(status='complete',errors=0)))
                    report=dict(rows=[dict(error=None,result=dict(joint_rc_zero_screen_passed=True))]) if kind=='zero' else dict(comparison=dict(joint_rc_sparse_feasibility_passed=True))
                    (artifact/'summary.json').write_text(json.dumps(report))
                    kwargs['stdout'].write('/work/OpenLVDS/'+str(artifact.relative_to(root))+'\n')
            output=root/'chain'
            with patch.object(p,'unit_info',side_effect=[self.active(),self.collected()]),patch.object(p.subprocess,'run',side_effect=execute) as commands:
                p.run('existing.service',log,bank,output)
            state=json.loads((output/'state.json').read_text());self.assertEqual(state['status'],'three_point_complete')
            self.assertEqual(state['producer_invocation'],'original');self.assertEqual(commands.call_count,4)
            self.assertFalse(state['qualified_phy'])

    def test_collected_service_without_passing_artifact_never_starts_consumers(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            root=Path(directory);log=root/'producer.log';log.write_text('')
            with patch.object(p,'unit_info',side_effect=[self.active(),self.collected()]),patch.object(p.subprocess,'run') as commands:
                with self.assertRaises(ValueError):p.run('existing.service',log,root/'bank',root/'chain')
            commands.assert_not_called();self.assertEqual(json.loads((root/'chain/state.json').read_text())['status'],'failed')
        with self.assertRaises(ValueError):p.producer_live_or_reaped(dict(self.active(),InvocationID='replacement'),'original')
        with self.assertRaises(ValueError):p.producer_live_or_reaped(dict(self.active(),InvocationID=''),'original')


if __name__=='__main__':unittest.main()
