# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_unclamped_receiver as selected


class UnclampedFollowupSelection(unittest.TestCase):
    def test_tail_profile_requires_exact_width_and_dispatches_its_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);replay,identity=self.fixture(root)
            identity.update(clamp_variant='unclamped_tail_headroom',decision_tail_width_um=16,
                            decision_tail_scale=0.25,first_restoration_nfet_model='sky130_fd_pr__nfet_01v8')
            (replay/'manifest.json').write_text(json.dumps(dict(identity=identity)))
            with patch.object(selected,'ROOT',root),patch.object(selected.tail_native,'run') as verify:
                with selected.selection(replay):
                    self.assertIs(selected.link.source_variant,selected.tail_source)
                    self.assertIn('probe_receiver_tail_headroom_candidate.py',selected.components.CODE)
                    self.assertIn('receiver_tail_headroom_matrix.py',selected.link.CODE)
                    selected.link.recheck_replay(replay)
                    verify.assert_called_once_with(replay)
            for changes in [dict(decision_tail_width_um=64),dict(decision_tail_scale=1),
                            dict(clamp_variant='unclamped_fast_restore'),
                            dict(first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt')]:
                (replay/'manifest.json').write_text(json.dumps(dict(identity=dict(identity,**changes))))
                with patch.object(selected,'ROOT',root),self.assertRaises(ValueError):selected.selected_replay(replay)

    def test_lvt_profile_requires_its_exact_model_and_native_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            replay, identity = self.fixture(root)
            identity.update(clamp_variant='unclamped_lvt_restore',
                            first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt')
            (replay / 'manifest.json').write_text(json.dumps(dict(identity=identity)))
            with patch.object(selected, 'ROOT', root), patch.object(selected.lvt_native, 'run') as verify:
                with selected.selection(replay):
                    self.assertIs(selected.link.source_variant, selected.lvt_source)
                    self.assertIn('probe_receiver_lvt_restore_candidate.py', selected.components.CODE)
                    self.assertIn('layout_receiver_lvt_restore_candidate.py', selected.link.CODE)
                    selected.link.recheck_replay(replay)
                    verify.assert_called_once_with(replay)
            for change in [dict(first_restoration_nfet_model='sky130_fd_pr__nfet_01v8'),
                           dict(clamp_variant='unclamped_fast_restore')]:
                modified = dict(identity, **change)
                (replay / 'manifest.json').write_text(json.dumps(dict(identity=modified)))
                with patch.object(selected, 'ROOT', root), self.assertRaisesRegex(ValueError, 'NFET model'):
                    selected.selected_replay(replay)

    def fixture(self, root):
        replay = root / 'build/diagnostics/receiver_replay/selected'
        replay.mkdir(parents=True)
        identity = dict(clamp_variant='unclamped_fast_restore', decision_clamped=False, parallel_clamp_units=0,
                        clamp_reference=None, replica_monitor_unloaded=True, input_tail_scale=2, decision_scale=1,
                        restoration_widths_um=[[8, 4], [16, 8], [16, 8]])
        (replay / 'manifest.json').write_text(json.dumps(dict(identity=identity)))
        return replay, identity

    def test_exact_native_selector_and_source_are_captured_and_restored_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            replay, _ = self.fixture(root)
            before = (selected.link.source_variant, selected.link.recheck_replay,
                      selected.link.CODE, selected.components.CODE)
            with patch.object(selected, 'ROOT', root), patch.object(selected.native, 'run') as verify:
                with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                    with selected.selection(replay):
                        self.assertIs(selected.link.source_variant, selected.source_variant)
                        selected.link.recheck_replay(replay)
                        verify.assert_called_once_with(replay)
                        for names in [selected.link.CODE, selected.components.CODE]:
                            self.assertIn('qualify_unclamped_receiver.py', names)
                            self.assertIn('probe_receiver_unclamped_restore_candidate.py', names)
                        raise RuntimeError('fixture failure')
            self.assertEqual((selected.link.source_variant, selected.link.recheck_replay,
                              selected.link.CODE, selected.components.CODE), before)

    def test_clamped_or_wrong_stage_metadata_cannot_select_followup(self):
        for change in [dict(decision_clamped=True), dict(parallel_clamp_units=2), dict(clamp_reference='VREF'),
                       dict(clamp_variant='vref_fast_restore'), dict(restoration_widths_um=[[4, 2], [8, 4], [16, 8]])]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                replay, identity = self.fixture(root)
                identity.update(change)
                (replay / 'manifest.json').write_text(json.dumps(dict(identity=identity)))
                with patch.object(selected, 'ROOT', root), self.assertRaisesRegex(ValueError, 'exact unclamped'):
                    with selected.selection(replay):
                        self.fail('Invalid metadata entered follow-up')


if __name__ == '__main__':
    unittest.main()
