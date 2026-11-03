# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_driver_cmfb_lead_components as flow


class CompensatedComponentHandoff(unittest.TestCase):
    def test_live_owner_must_remain_the_same_invocation(self):
        expected = dict(MainPID='123', ActiveState='active', InvocationID='first')
        self.assertTrue(flow.owned(expected, expected))
        self.assertFalse(flow.owned({'MainPID': '0'}, expected))
        with self.assertRaisesRegex(ValueError, 'owner changed'):
            flow.owned(dict(expected, InvocationID='restart', MainPID='124'), expected)

    def witness(self, root, wrong_pilot=False, passed=True):
        parent = root / 'parent'
        parent.mkdir(exist_ok=True)
        pilot = 'build/diagnostics/driver_compact_native_pilot/' + 'a' * 16
        p = root / pilot
        p.mkdir(parents=True, exist_ok=True)
        (p / 'manifest.json').write_text('{}')
        (p / 'summary.json').write_text(json.dumps(dict(native_output_pilot_passed=passed,
            required_cases=6, required_pvt=3, passed_pvt=3 if passed else 0,
            manifest_sha256=flow.sha(p / 'manifest.json'))))
        full = 'build/diagnostics/driver_compact_native/' + 'b' * 16
        f = root / full
        f.mkdir(parents=True, exist_ok=True)
        (f / 'manifest.json').write_text(json.dumps({'identity': {
            'pilot': 'different-pilot' if wrong_pilot else pilot,
            'inputs': {pilot + '/' + name: flow.sha(p / name) for name in ['manifest.json', 'summary.json']}}}))
        (parent / 'prepare-native-full.json').write_text(json.dumps(dict(artifact=full,
            manifest_sha256=flow.sha(f / 'manifest.json'))))
        return parent, pilot

    def test_live_owner_alone_cannot_admit_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(flow.ready(Path(tmp), 'pilot'))

    def test_verified_matrix_witness_requires_matching_complete_pilot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(flow, 'ROOT', root):
                parent, pilot = self.witness(root)
                self.assertTrue(flow.ready(parent, pilot))
                self.witness(root, passed=False)
                self.assertFalse(flow.ready(parent, pilot))
                self.witness(root, wrong_pilot=True)
                with self.assertRaisesRegex(ValueError, 'another pilot'):
                    flow.ready(parent, pilot)

    def test_modified_full_matrix_witness_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(flow, 'ROOT', root):
                parent, pilot = self.witness(root)
                witness = json.loads((parent / 'prepare-native-full.json').read_text())
                (root / witness['artifact'] / 'manifest.json').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'selection changed'):
                    flow.ready(parent, pilot)

    def exercise(self, passed=True, parent_failed=False, failed_live_parent=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent, pilot = self.witness(root)
            (parent / 'manifest.json').write_text('{}')
            if parent_failed or failed_live_parent:
                (parent / 'summary.json').write_text(json.dumps(dict(status='held_compensated_native_pilot_failed',
                    manifest_sha256=flow.sha(parent / 'manifest.json'))))
            identity = dict(parent='parent', pilot=pilot, assembly='assembly', unit='native.service',
                owner=dict(MainPID='123', ActiveState='active', InvocationID='first'), inputs={})
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            out = root / 'build/diagnostics' / flow.NAMESPACE / digest
            out.mkdir(parents=True)
            (out / 'manifest.json').write_text(json.dumps({'identity': identity}))
            calls = []

            def child(args, **kwargs):
                action = args[5]
                calls.append(action)
                if action == 'prepare':
                    relative = 'build/diagnostics/driver_compact_components/' + 'c' * 16
                    folder = root / relative
                    folder.mkdir(parents=True)
                    (folder / 'manifest.json').write_text('{}')
                    (folder / 'summary.json').write_text(json.dumps(dict(passed=passed, required=30,
                        passed_cases=30 if passed else 29, manifest_sha256=flow.sha(folder / 'manifest.json'))))
                    kwargs['stdout'].write('/work/OpenLVDS/' + relative + '\n')
                class Result:
                    def check_returncode(self):
                        pass
                return Result()

            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner',
                    return_value={'MainPID': '0'} if parent_failed else identity['owner']), \
                    patch.object(flow.subprocess, 'run', side_effect=child):
                flow.run(out)
                result = json.loads((out / 'summary.json').read_text())
                self.assertFalse(result['qualified_phy'])
                with self.assertRaisesRegex(ValueError, 'Prior'):
                    flow.run(out)
            return calls, result

    def test_failed_native_parent_dispatches_nothing(self):
        calls, result = self.exercise(parent_failed=True)
        self.assertEqual(calls, [])
        self.assertEqual(result['status'], 'held_native_prerequisite_failed')

    def test_failed_parent_receipt_stops_dispatch_even_before_owner_exit(self):
        calls, result = self.exercise(failed_live_parent=True)
        self.assertEqual(calls, [])
        self.assertEqual(result['status'], 'held_native_prerequisite_failed')

    def test_failed_long_components_cannot_be_verified_as_ready(self):
        calls, result = self.exercise(passed=False)
        self.assertEqual(calls, ['prepare', 'run'])
        self.assertEqual(result['status'], 'held_long_components_failed')

    def test_successful_parallel_handoff_requires_independent_final_verification(self):
        calls, result = self.exercise()
        self.assertEqual(calls, ['prepare', 'run', 'verify'])
        self.assertTrue(result['components_passed'])
        self.assertEqual(result['status'], 'completed_long_components')
