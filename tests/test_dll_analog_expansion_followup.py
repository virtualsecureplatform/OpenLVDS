import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_dll_analog_expansion as followup


class AnalogExpansionHandoff(unittest.TestCase):
    def test_running_state_never_dispatches_or_verifies_partial_results(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / followup.expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True); (parent / 'state.json').write_text(json.dumps(dict(status='screening_analog_timing')))
            with patch.object(followup, 'ROOT', root), patch.object(followup.expansion.screen, 'verify') as verify, \
                 patch.object(followup.expansion, 'prepare') as prepare:
                with self.assertRaises(ValueError): followup.followup(parent)
                verify.assert_not_called(); prepare.assert_not_called()

    def test_no_survivor_records_hold_without_dispatch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / followup.expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True)
            for n in ('manifest.json', 'summary.json'): (parent / n).write_text('{}')
            (parent / 'state.json').write_text(json.dumps(dict(status='held_analog_timing_failed')))
            with patch.object(followup, 'ROOT', root), patch.object(followup, 'sha', return_value='hash'), \
                 patch.object(followup.expansion.screen, 'verify', return_value=dict(ranked_survivors=[])), \
                 patch.object(followup.expansion, 'prepare') as prepare:
                out = followup.followup(parent)
                self.assertEqual(json.loads((out / 'state.json').read_text())['status'], 'held_no_analog_timing_survivor')
                prepare.assert_not_called()
                with self.assertRaises(ValueError): followup.followup(parent)

    def test_complete_success_orders_prepare_run_and_independent_verify(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / followup.expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True)
            for n in ('manifest.json', 'summary.json'): (parent / n).write_text('{}')
            (parent / 'state.json').write_text(json.dumps(dict(status='analog_timing_screened')))
            child = root / 'child'; child.mkdir(); (child / 'summary.json').write_text('{}')
            events = []
            with patch.object(followup, 'ROOT', root), patch.object(followup, 'sha', return_value='hash'), \
                 patch.object(followup.expansion.screen, 'verify', return_value=dict(ranked_survivors=['tail140_w20'])), \
                 patch.object(followup.expansion, 'prepare', side_effect=lambda p: events.append('prepare') or child), \
                 patch.object(followup.expansion, 'run', side_effect=lambda p: events.append('run')), \
                 patch.object(followup.expansion, 'verify', side_effect=lambda p: events.append('verify') or dict(analog_source_expansion_passed=True)):
                out = followup.followup(parent)
                self.assertEqual(events, ['prepare', 'run', 'verify'])
                self.assertTrue(json.loads((out / 'state.json').read_text())['passed'])

    def test_incomplete_terminal_evidence_cannot_start_expansion(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / followup.expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True); (parent / 'state.json').write_text(json.dumps(dict(status='analog_timing_screened')))
            with patch.object(followup, 'ROOT', root), \
                 patch.object(followup.expansion.screen, 'verify', side_effect=ValueError('incomplete raw waveform')), \
                 patch.object(followup.expansion, 'prepare') as prepare:
                with self.assertRaises(ValueError): followup.followup(parent)
                prepare.assert_not_called()
