# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_candidate_link as diagnostic
from spice_scope import closure_hash


class ReceiverLinkDiagnostic(unittest.TestCase):
    def test_clamped_replay_uses_its_own_exact_waveform_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'manifest.json').write_text('{"identity":{"decision_clamped":true}}')
            with patch('probe_receiver_clamp_candidate.run') as clamp,patch('probe_receiver_gain_candidate.run') as gain:
                diagnostic.recheck_replay(root)
            clamp.assert_called_once_with(root);gain.assert_not_called()

    def test_receiver_swap_preserves_all_other_macros_and_terminal_order(self):
        ports=['P','N','Q','NB','PB','VDDIO','VDDD','VSS','ENABLE']
        receiver='.subckt openlvds_receiver_core '+' '.join(ports)+'\nR1 Q VSS 10k\n.ends openlvds_receiver_core\n'
        protected=['openlvds_driver','lvds_bias','openlvds_dll','openlvds_delay_line','openlvds_tx_core','openlvds_ddr_rx']
        baseline=receiver+''.join(f'.subckt {n} A Y\nR1 A Y 1k\n.ends {n}\n' for n in protected)
        candidate=receiver.replace('10k','20k')
        result=diagnostic.receiver_overlay(baseline,candidate,ports)
        self.assertEqual(closure_hash(result,'openlvds_receiver_core'),closure_hash(candidate,'openlvds_receiver_core'))
        for name in protected:self.assertEqual(closure_hash(result,name),closure_hash(baseline,name))
        with self.assertRaisesRegex(ValueError,'terminal order'):
            diagnostic.receiver_overlay(baseline,candidate,ports[::-1])

    def fixture(self,root,results):
        (root/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
        for name in ['captured','sharp_control']:
            (root/name).mkdir();(root/name/'summary.json').write_text('{}')

    def test_incomplete_replay_cannot_start_a_simulation_through_recheck(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(diagnostic,'recheck_replay') as recheck:
            root=Path(temp);(root/'summary.json').write_text('{"diagnostic_complete":true}')
            with self.assertRaisesRegex(ValueError,'must complete first'):diagnostic.replay_ready(root)
            recheck.assert_not_called()

    def test_completed_replay_is_reverified_and_missing_edges_hold_link(self):
        results=[dict(task=name,receiver_transport=dict(missing_output_edges=count,
                 pulses=[dict(output_edges_in_next_input_period=1)]))
                 for name,count in [('captured',1),('sharp_control',0)]]
        with tempfile.TemporaryDirectory() as temp, patch.object(diagnostic,'recheck_replay') as recheck:
            root=Path(temp);self.fixture(root,results)
            with self.assertRaisesRegex(ValueError,'clock edges'):diagnostic.replay_ready(root)
            recheck.assert_called_once_with(root)
            results[0]['receiver_transport']['missing_output_edges']=0
            (root/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
            diagnostic.replay_ready(root)

    def test_no_missing_edges_does_not_allow_extra_clock_pulses(self):
        results=[dict(task=name,receiver_transport=dict(missing_output_edges=0,
                 pulses=[dict(output_edges_in_next_input_period=2 if name=='captured' else 1)]))
                 for name in ['captured','sharp_control']]
        with tempfile.TemporaryDirectory() as temp, patch.object(diagnostic,'recheck_replay'):
            root=Path(temp);self.fixture(root,results)
            with self.assertRaisesRegex(ValueError,'repeats clock edges'):diagnostic.replay_ready(root)

    def test_duplicate_replay_case_cannot_supply_coverage(self):
        results=[dict(task='captured',receiver_transport=dict(missing_output_edges=0))]*2
        with tempfile.TemporaryDirectory() as temp, patch.object(diagnostic,'recheck_replay'):
            root=Path(temp);self.fixture(root,results)
            with self.assertRaisesRegex(ValueError,'coverage is incomplete'):diagnostic.replay_ready(root)
