import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_rx_clock_skew as followup

OWNER = dict(MainPID='123', ActiveState='active', InvocationID='same', ExecStart='exact original producer')


class ClockSkewHandoff(unittest.TestCase):
    def context(self, root, state):
        capture = root / 'capture'; capture.mkdir(); (capture / 'state.json').write_text(json.dumps(state))
        identity = dict(parent='parent', aperture='capture', unit='owner.service', owner=OWNER, inputs={}, no_outer_lease=True)
        out = root / 'build/diagnostics' / followup.NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        out.mkdir(parents=True); (out / 'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False)))
        return out, capture

    def test_exact_owner_binding_rejects_pid_reuse_and_changed_invocation(self):
        self.assertTrue(followup.same_owner(OWNER, OWNER))
        for key, value in [('MainPID', '456'), ('InvocationID', 'restarted'), ('ExecStart', 'other producer'), ('ActiveState', 'inactive')]:
            changed = dict(OWNER); changed[key] = value
            self.assertFalse(followup.same_owner(OWNER, changed))

    def test_complete_state_without_a_table_cannot_be_ready(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); out, capture = self.context(root, dict(status='complete', passed=True))
            self.assertFalse(followup.ready(capture))
            (capture / 'table.json').write_text('{}'); self.assertTrue(followup.ready(capture))
            (capture / 'state.json').write_text(json.dumps(dict(status='complete', passed=False)))
            self.assertFalse(followup.ready(capture))

    def test_failed_aperture_holds_without_dispatch_or_owner_restart(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); out, capture = self.context(root, dict(status='held_by_native_failure'))
            with patch.object(followup, 'ROOT', root), patch.object(followup, 'invoke') as invoke, patch.object(followup, 'owner') as owner:
                followup.run(out); invoke.assert_not_called(); owner.assert_not_called()
                self.assertEqual(json.loads((out / 'state.json').read_text())['status'], 'held_aperture_not_passed')
                with self.assertRaises(ValueError): followup.run(out)

    def test_disappeared_owner_without_complete_evidence_holds(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); out, capture = self.context(root, dict(status='running_full'))
            with patch.object(followup, 'ROOT', root), patch.object(followup, 'invoke') as invoke, \
                 patch.object(followup, 'owner', return_value=dict(MainPID='0', ActiveState='inactive')):
                followup.run(out); invoke.assert_not_called()
                self.assertIn('owner_changed', json.loads((out / 'state.json').read_text())['status'])

    def test_transient_observation_timeout_repolls_before_gated_prepare_run_verify(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); out, capture = self.context(root, dict(status='running_full'))
            relative = Path('build/diagnostics') / followup.probe.NAMESPACE / 'child'
            child = root / relative; child.mkdir(parents=True)
            (child / 'summary.json').write_text(json.dumps(dict(clock_skew_source_passed=True, ranked_survivors=['n065'])))
            events = []
            def invoke(out, args, label):
                events.append(label)
                return '/work/OpenLVDS/' + str(relative) if label == 'prepare' else '{}'
            with patch.object(followup, 'ROOT', root), patch.object(followup, 'ready', side_effect=[False, True]), \
                 patch.object(followup, 'owner', side_effect=subprocess.TimeoutExpired('systemctl', 1)), \
                 patch.object(followup.time, 'sleep') as wait, \
                 patch.object(followup, 'invoke', side_effect=invoke):
                followup.run(out)
                self.assertEqual(events, ['prepare', 'run', 'verify']); wait.assert_called_once_with(20)
                self.assertTrue(json.loads((out / 'state.json').read_text())['passed'])

    def test_science_executes_in_pinned_container_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with patch.object(followup, 'ROOT', root), patch.object(followup.subprocess, 'run') as run:
                followup.invoke(root, ['verify', 'build/diagnostics/fixture'], 'verify')
                self.assertEqual(run.call_args.args[0][:4], [str(root / 'scripts/env.sh'), '--ngspice', '/usr/bin/python3', 'scripts/probe_rx_clock_skew.py'])
                self.assertEqual(run.call_args.kwargs['cwd'], root)
            for output in ('/tmp/elsewhere', '/work/OpenLVDS/build/diagnostics/rx_clock_skew_source/../../escape'):
                with self.assertRaises(ValueError): followup.prepared_child(output)
