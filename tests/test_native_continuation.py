# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_native_dll as continuation


class NativeContinuation(unittest.TestCase):
    def test_host_wait_rejects_changed_producer_without_starting_science(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); scripts = root/'scripts'; scripts.mkdir()
            for name in ['continue_native_dll.py','advance_ota_candidate.py','dll_native_evidence.py']:
                (scripts/name).write_text('original')
            q = root/'build/diagnostics/dll_qualification/selected'; q.mkdir(parents=True)
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(variant='ota_w8_c4'))))
            handoff = root/'build/diagnostics/dll_layout/selected/native_handoff.json'
            handoff.parent.mkdir(parents=True)
            handoff.write_text(json.dumps(dict(identity={}, status='run_native_screen')))
            def changed(_):
                (scripts/'continue_native_dll.py').write_text('changed')
            with patch.object(continuation,'ROOT',root), patch.object(continuation,'CODE',[]), \
                 patch.object(continuation,'PRODUCERS',set()), \
                 patch.object(continuation,'validate') as validate, \
                 patch.object(continuation.time,'sleep',side_effect=changed), \
                 patch.object(continuation.subprocess,'run',return_value=Mock(stdout='active')) as run:
                with self.assertRaisesRegex(ValueError,'producer changed'):
                    continuation.run(q,handoff,'producer.service')
            validate.assert_not_called()
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[0][0],'systemctl')
            self.assertEqual(json.loads((q/'continuation/state.json').read_text())['status'],
                             'held_for_diagnosis')

    def test_container_cannot_start_a_host_service_wait(self):
        with patch.object(continuation,'ROOT',Path('/work/OpenLVDS')):
            with self.assertRaisesRegex(ValueError,'waiting job on the host'):
                continuation.run(Path('/missing'),Path('/missing'),'producer.service')

    def test_handoff_must_pass_match_and_exit(self):
        receipt = dict(status='native_screen_passed', qualification='selected')
        self.assertFalse(continuation.screen_ready(receipt, 'selected', True))
        self.assertTrue(continuation.screen_ready(receipt, 'selected', False))
        with self.assertRaisesRegex(ValueError, 'another qualification'):
            continuation.screen_ready(receipt, 'other', False)
        with self.assertRaisesRegex(ValueError, 'ended before passing'):
            continuation.screen_ready(dict(status='run_native_screen'), 'selected', False)
        with self.assertRaisesRegex(ValueError, 'held'):
            continuation.screen_ready(dict(status='held_for_diagnosis'), 'selected', True)

    def test_failed_model_never_expands_native_matrix(self):
        model = Mock(side_effect=ValueError('model failed'))
        execute = Mock(); native = Mock()
        with self.assertRaisesRegex(ValueError, 'model failed'):
            continuation.progression(continuation.ROOT/'build/qualification', model, execute, native)
        execute.assert_not_called(); native.assert_not_called()
        model.assert_called_once_with(False)

    def test_native_failure_holds_all_pvt_models(self):
        root = continuation.ROOT
        model = Mock(return_value=root/'build/model.json')
        execute = Mock(side_effect=ValueError('native failed')); native = Mock()
        with self.assertRaisesRegex(ValueError, 'native failed'):
            continuation.progression(root/'build/qualification', model, execute, native)
        model.assert_called_once_with(False); native.assert_not_called()

    def test_native_evidence_is_verified_before_all_pvt_expansion(self):
        root = continuation.ROOT
        model = Mock(return_value=root/'build/model.json'); execute = Mock()
        native = Mock(side_effect=ValueError('damaged waveform'))
        with self.assertRaisesRegex(ValueError, 'damaged waveform'):
            continuation.progression(root/'build/qualification', model, execute, native)
        model.assert_called_once_with(False)

    def test_success_uses_explicit_model_and_original_native_limits(self):
        root = continuation.ROOT; qualification = root/'build/qualification'
        report = root/'build/model.json'; events = Mock()
        events.model.return_value = report
        result = continuation.progression(qualification, events.model, events.execute, events.verify)
        self.assertEqual(result, report)
        self.assertEqual(events.mock_calls, [call.model(False),
            call.execute('native_full', 'qualify_dll_candidate.py', [
                'run', 'build/qualification', '--stage', 'full', '--jobs', '3',
                '--stability', 'build/model.json']),
            call.verify(qualification), call.model(True)])
