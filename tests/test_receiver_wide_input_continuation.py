# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_receiver_wide_input import artifact,source_finished


class WideInputContinuation(unittest.TestCase):
    def test_live_owner_remains_pending_even_if_summary_is_present(self):
        for state in ['active','activating','deactivating']:
            self.assertFalse(source_finished(dict(ActiveState=state),True))

    def test_terminal_success_requires_all_reports(self):
        observation=dict(ActiveState='inactive',LoadState='loaded',Result='success',ExecMainStatus='0')
        self.assertTrue(source_finished(observation,True))
        with self.assertRaisesRegex(ValueError,'all source reports'):source_finished(observation,False)

    def test_missing_or_failed_owner_cannot_advance_even_with_reports(self):
        for observation in [dict(LoadState='not-found',ActiveState='inactive'),
                            dict(LoadState='loaded',ActiveState='failed',Result='exit-code',ExecMainStatus='1'),
                            dict(LoadState='loaded',ActiveState='inactive',Result='success',ExecMainStatus='2')]:
            with self.assertRaisesRegex(ValueError,'successfully'):source_finished(observation,True)

    def test_container_artifact_is_mapped_only_into_expected_host_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(artifact('/work/OpenLVDS/build/diagnostics/receiver_layout/test','receiver_layout',root),
                             root/'build/diagnostics/receiver_layout/test')
            for value in ['/tmp/test','/work/OpenLVDS/build/diagnostics/receiver_replay/test',
                          '/work/OpenLVDS/build/diagnostics/receiver_layout/../../escape']:
                with self.assertRaisesRegex(ValueError,'Unexpected'):artifact(value,'receiver_layout',root)
