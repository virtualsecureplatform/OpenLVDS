# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import driver_restore_precision_retry as retry


class DriverRestorePrecisionRetry(unittest.TestCase):
    def test_only_maximum_step_changes_with_original_duration_output_and_whitespace(self):
        deck='Title\nVD VDDD 0 1.8\n.tran  20p 188.049n 0   100p  \n.print tran V(P)\n.end\n'
        result=retry.tighten(deck)
        self.assertEqual(result.replace('0   1p  ','0   100p  '),deck)
        with patch.object(retry,'ORIGINAL_FIXTURE',return_value=(deck,{'probe':'same'})):
            self.assertEqual(retry.fixture('parent',Path('/old'),Path('/new')),(result,{'probe':'same'}))

    def test_rejects_shortened_shifted_output_or_different_maximum_fixtures(self):
        base='.tran 20p 188.049n 0 100p\n'
        for deck in [base+base,base.replace('20p','10p'),base.replace('188.049n','120n'),
                     base.replace(' 0 ',' 5n '),base.replace('100p','20p'),base.replace('100p','1p')]:
            with self.assertRaises(ValueError):retry.tighten(deck)

    def test_selection_restores_original_producer_even_after_failure(self):
        code,fixture=retry.comparison.CODE,retry.comparison.fixture
        with self.assertRaisesRegex(RuntimeError,'fixture'):
            with retry.selection():
                self.assertIn(Path(retry.__file__).name,retry.comparison.CODE)
                self.assertIs(retry.comparison.fixture,retry.fixture)
                raise RuntimeError('fixture')
        self.assertIs(retry.comparison.CODE,code)
        self.assertIs(retry.comparison.fixture,fixture)

    def test_policy_binds_current_manifest_and_refuses_tampering_before_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            manifest=dict(identity=dict(parent='captured_parent',code={
                Path(retry.__file__).name:retry.comparison.digest(Path(retry.__file__))}))
            (root/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(retry.comparison,'prepare',return_value=root):
                retry.run('prepare',Path('/parent'))
                before=(root/'manifest.json').read_bytes(),(root/'numerical_policy.json').read_bytes()
                retry.run('prepare',Path('/parent'))
                self.assertEqual(before,((root/'manifest.json').read_bytes(),(root/'numerical_policy.json').read_bytes()))
            with patch.object(retry.comparison,'run') as run:
                retry.run('run',root)
                run.assert_called_once_with(root)
                policy=json.loads((root/'numerical_policy.json').read_text());policy['maximum_step_ps']=20
                (root/'numerical_policy.json').write_text(json.dumps(policy))
                run.reset_mock()
                with self.assertRaisesRegex(ValueError,'policy changed'):retry.run('run',root)
                run.assert_not_called()


if __name__=='__main__':unittest.main()
