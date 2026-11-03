# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_compensated_coupled as flow


class JoinedCoupledQualifications(unittest.TestCase):
    NATIVE = dict(native_output_matrix_passed=True, required_cases=30, required_pvt=15, passed_pvt=15)
    COMPONENTS = dict(passed=True, required=30, passed_cases=30)

    def test_both_complete_matrices_required(self):
        self.assertTrue(flow.prerequisites(self.NATIVE, self.COMPONENTS))
        self.assertFalse(flow.prerequisites(dict(self.NATIVE, required_cases=6, required_pvt=3), self.COMPONENTS))
        self.assertFalse(flow.prerequisites(self.NATIVE, dict(self.COMPONENTS, passed_cases=29)))
        self.assertFalse(flow.prerequisites(self.NATIVE, dict(self.COMPONENTS, passed=False)))

    def test_live_owner_and_partial_receipts_cannot_trigger_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = dict(artifact='matrix', parent='parent', unit='native.service',
                owner=dict(MainPID='123', InvocationID='first'))
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner', return_value=source['owner']):
                self.assertIsNone(flow.terminal_source(source, 'native'))
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner', return_value={'MainPID': '0'}):
                with self.assertRaisesRegex(ValueError, 'without terminal'):
                    flow.terminal_source(source, 'native')
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner',
                    return_value=dict(MainPID='124', InvocationID='restart')):
                with self.assertRaisesRegex(ValueError, 'owner changed'):
                    flow.terminal_source(source, 'native')

    def test_terminal_controller_must_bind_the_scientific_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['matrix', 'parent']:
                (root / name).mkdir()
                (root / name / 'manifest.json').write_text('{}')
            (root / 'matrix/summary.json').write_text(json.dumps(dict(self.NATIVE,
                manifest_sha256=flow.sha(root / 'matrix/manifest.json'))))
            parent = dict(status='completed_compensated_native_matrix', artifact='matrix',
                report_sha256=flow.sha(root / 'matrix/summary.json'),
                manifest_sha256=flow.sha(root / 'parent/manifest.json'))
            (root / 'parent/summary.json').write_text(json.dumps(parent))
            source = dict(artifact='matrix', parent='parent', unit='native.service', owner={'MainPID': '123'})
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner', return_value={'MainPID': '0'}):
                self.assertTrue(flow.terminal_source(source, 'native')['native_output_matrix_passed'])
                parent['report_sha256'] = 'changed'
                (root / 'parent/summary.json').write_text(json.dumps(parent))
                self.assertIs(flow.terminal_source(source, 'native'), False)

    def test_different_driver_campaigns_are_rejected_before_queueing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parents = []
            owners = {}
            for label, parent_namespace, child_namespace, receipt, script, pilot in [
                    ('native', 'driver_cmfb_lead_physical_followup', 'driver_compact_native',
                     'prepare-native-full.json', 'continue_driver_cmfb_lead_physical.py', 'pilot-a'),
                    ('component', 'driver_cmfb_lead_component_followup', 'driver_compact_components',
                     'prepared.json', 'continue_driver_cmfb_lead_components.py', 'pilot-b')]:
                parent = root / 'build/diagnostics' / parent_namespace / ('a' * 16)
                child = root / 'build/diagnostics' / child_namespace / ('b' * 16)
                parent.mkdir(parents=True)
                child.mkdir(parents=True)
                (child / 'manifest.json').write_text(json.dumps({'identity': {'pilot': pilot}}))
                (parent / receipt).write_text(json.dumps(dict(artifact=str(child.relative_to(root)),
                    manifest_sha256=flow.sha(child / 'manifest.json'))))
                parents.append(parent)
                owners[label] = dict(MainPID='123', ActiveState='active',
                    ExecStart='python scripts/' + script + ' run ' + str(parent))
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner', side_effect=lambda unit: owners[unit]):
                with self.assertRaisesRegex(ValueError, 'different native pilots'):
                    flow.prepare(*parents, 'native', 'component', root / 'reference', root / 'receiver')
            self.assertFalse((root / 'build/diagnostics' / flow.NAMESPACE).exists())

    def exercise(self, owner_failed=False, matrix_failed=False, restored=True, complete=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = dict(sources={'native': {'artifact': 'native'}, 'components': {'artifact': 'components'}},
                reference='benchmark', receiver='receiver', inputs={})
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            out = root / 'build/diagnostics' / flow.NAMESPACE / digest
            out.mkdir(parents=True)
            (out / 'manifest.json').write_text(json.dumps({'identity': identity}))
            commands = []
            def terminal(source, label):
                if label == 'native':
                    if owner_failed:
                        return False
                    return dict(self.NATIVE, passed_pvt=14) if matrix_failed else self.NATIVE
                return self.COMPONENTS
            def child(args, **kwargs):
                action = args[5]
                commands.append(action)
                if action == 'prepare':
                    relative = 'build/diagnostics/compensated_coupled_restoration/' + 'a' * 16
                    folder = root / relative
                    folder.mkdir(parents=True)
                    (folder / 'manifest.json').write_text('{}')
                    rows = [dict(numerically_completed=True, error=None)] * (2 if complete else 1)
                    (folder / 'summary.json').write_text(json.dumps(dict(results=rows,
                        payload_restored=restored, manifest_sha256=flow.sha(folder / 'manifest.json'))))
                    kwargs['stdout'].write('/work/OpenLVDS/' + relative + '\n')
                return subprocess.CompletedProcess(args, 0)
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'terminal_source', side_effect=terminal), \
                    patch.object(flow.subprocess, 'run', side_effect=child):
                flow.run(out)
                report = json.loads((out / 'summary.json').read_text())
                self.assertFalse(report['qualified_phy'])
                with self.assertRaisesRegex(ValueError, 'Prior'):
                    flow.run(out)
            return commands, report

    def test_failed_controller_or_matrix_dispatches_nothing(self):
        for options in [dict(owner_failed=True), dict(matrix_failed=True)]:
            commands, result = self.exercise(**options)
            self.assertEqual(commands, [])
            self.assertTrue(result['status'].startswith('held_qualification'))

    def test_numerically_complete_failed_payload_is_verified_but_held(self):
        commands, result = self.exercise(restored=False)
        self.assertEqual(commands, ['prepare', 'run', 'verify'])
        self.assertFalse(result['payload_restored'])
        self.assertEqual(result['status'], 'held_coupled_diagnostic')

    def test_partial_numerical_output_cannot_be_verified_or_released(self):
        commands, result = self.exercise(complete=False)
        self.assertEqual(commands, ['prepare', 'run'])
        self.assertFalse(result['payload_restored'])

    def test_successful_diagnostic_requires_final_verification(self):
        commands, result = self.exercise()
        self.assertEqual(commands, ['prepare', 'run', 'verify'])
        self.assertTrue(result['payload_restored'])
        self.assertEqual(result['status'], 'completed_coupled_diagnostic')
