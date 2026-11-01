# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_tail_timestep_retry as retry


class ReceiverTimestepRetry(unittest.TestCase):
    DECK = 'VR VREF 0 1.2\n.tran 5p 80n 0 5p\n.print tran V(Q)\n.end\n'

    def fixture(self,root):
        tasks=[]
        for name in ['unclamped_captured','clamped_captured','clamped_sharp_control']:
            folder=root/name;folder.mkdir()
            (folder/'bench.cir').write_text(self.DECK)
            (folder/'candidate.spice').write_text('* unchanged receiver\n')
            tasks.append(dict(id=name,files={n:retry.digest(folder/n) for n in ['bench.cir','candidate.spice']}))
        manifest=dict(identity=dict(parent='build/diagnostics/clock_restore/original',
            code={retry.NAME:retry.digest(Path(retry.__file__))}),tasks=tasks)
        (root/'manifest.json').write_text(json.dumps(manifest))
        return tasks

    def test_only_maximum_step_changes_and_conversion_is_idempotent(self):
        after=retry.tighten(self.DECK)
        self.assertEqual(after,self.DECK.replace('.tran 5p 80n 0 5p','.tran 5p 80n 0 1p'))
        self.assertEqual(retry.tighten(after),after)

    def test_different_original_stop_output_step_or_maximum_is_rejected(self):
        for deck in [self.DECK.replace('80n','79n'),self.DECK.replace('.tran 5p','.tran 10p'),
                     self.DECK.replace('0 5p','0 2p'),self.DECK.replace('.end','.tran 5p 80n 0 5p\n.end')]:
            with self.subTest(deck=deck),self.assertRaises(ValueError):retry.tighten(deck)

    def test_all_three_controls_tighten_and_repreparation_preserves_manifest_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tasks=self.fixture(root)
            retry.prepare_controls(root)
            before=(root/'manifest.json').read_bytes()
            policy_before=(root/'numerical_policy.json').read_bytes()
            for task in tasks:
                self.assertIn('.tran 5p 80n 0 1p',(root/task['id']/'bench.cir').read_text())
                self.assertEqual((root/task['id']/'candidate.spice').read_text(),'* unchanged receiver\n')
            retry.prepare_controls(root)
            self.assertEqual((root/'manifest.json').read_bytes(),before)
            self.assertEqual((root/'numerical_policy.json').read_bytes(),policy_before)

    def test_changed_fixture_is_rejected_before_rewriting_any_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tasks=self.fixture(root);before=(root/'manifest.json').read_bytes()
            (root/tasks[0]['id']/'bench.cir').write_text(self.DECK.replace('1.2','1.3'))
            with self.assertRaisesRegex(ValueError,'fixture changed'):retry.prepare_controls(root)
            self.assertEqual((root/'manifest.json').read_bytes(),before)
            self.assertFalse((root/'numerical_policy.json').exists())

    def test_no_executed_control_can_be_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tasks=self.fixture(root);before=(root/'manifest.json').read_bytes()
            (root/tasks[-1]['id']/'execution.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'executed receiver fixture'):retry.prepare_controls(root)
            self.assertEqual((root/'manifest.json').read_bytes(),before)
            for task in tasks:self.assertEqual((root/task['id']/'bench.cir').read_text(),self.DECK)


if __name__=='__main__':unittest.main()
