# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_driver_cmfb_lead_physical as flow


class CompensatedPhysicalHandoff(unittest.TestCase):
    def test_exact_source_owner_and_terminal_receipt_required(self):
        handoff = Path('/root/source-handoff')
        live = dict(MainPID='123', ActiveState='active', InvocationID='first',
            ExecStart='python scripts/continue_driver_cmfb_lead_source.py run ' + str(handoff))
        flow.admissible_owner(live, handoff, False)
        for invalid in [dict(live, ExecStart='other.py'), dict(live, ActiveState='failed'), {'MainPID': '0'}]:
            with self.assertRaises(ValueError):
                flow.admissible_owner(invalid, handoff, False)
        flow.admissible_owner({'MainPID': '0'}, handoff, True)
        with self.assertRaises(ValueError):
            flow.wait_state(dict(live, MainPID='124', InvocationID='restart'), live, True)

    def test_matrix_gate_rejects_partial_coverage_and_nonboolean_pass(self):
        complete = dict(passed=True, required_cases=30, required_pvt=15, passed_pvt=15)
        self.assertTrue(flow.matrix_passed(complete, 'passed', 30, 15))
        for changes in [dict(passed=1), dict(required_cases=6), dict(passed_pvt=14), dict(required_pvt=3)]:
            self.assertFalse(flow.matrix_passed(dict(complete, **changes), 'passed', 30, 15))

    def test_readiness_must_come_from_the_successful_matching_source_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, handoff = root / 'matrix', root / 'handoff'
            for folder in [source, handoff]:
                folder.mkdir()
                (folder / 'manifest.json').write_text('{}')
            (source / 'summary.json').write_text('{}')
            (handoff / 'summary.json').write_text(json.dumps(dict(
                status='completed_actual_source_matrix', source_waveform_matrix_passed=True,
                artifact='matrix', report_sha256=flow.sha(source / 'summary.json'),
                manifest_sha256=flow.sha(handoff / 'manifest.json'))))
            relative = 'build/diagnostics/driver_cmfb_lead_source_verification/' + 'a' * 16 + '/summary.json'
            ready = root / relative
            ready.parent.mkdir(parents=True)
            ready.write_text(json.dumps({'campaign': 'matrix'}))
            (handoff / 'verify-full.log').write_text('/work/OpenLVDS/' + relative + '\n')
            with patch.object(flow, 'ROOT', root):
                self.assertEqual(flow.source_readiness(source, handoff), relative)
                ready.write_text(json.dumps({'campaign': 'another-matrix'}))
                with self.assertRaisesRegex(ValueError, 'another source matrix'):
                    flow.source_readiness(source, handoff)
                (source / 'summary.json').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'successful bound'):
                    flow.source_readiness(source, handoff)

    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'build/diagnostics/driver_shape_source' / ('f' * 16)

            def receipt(folder, value):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'manifest.json').write_text('{}')
                (folder / 'summary.json').write_text(json.dumps(dict(value,
                    manifest_sha256=flow.sha(folder / 'manifest.json'))))

            def matrix(flag, cases, points, passed):
                return {flag: passed, 'required_cases': cases, 'required_pvt': points,
                    'passed_pvt': points if passed else 0}

            receipt(source, matrix('source_waveform_matrix_passed', 30, 15, failure != 'source'))
            identity = dict(source=str(source.relative_to(root)), source_handoff='source-owner',
                tiles='tiles', unit='source.service', owner=dict(MainPID='123'), inputs={})
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            out = root / 'build/diagnostics' / flow.NAMESPACE / digest
            out.mkdir(parents=True)
            (out / 'manifest.json').write_text(json.dumps({'identity': identity}))
            commands = []

            def child(args, **kwargs):
                script, arguments = Path(args[4]).name, args[5:]
                commands.append((script, arguments[0]))
                folder = None
                if script == flow.BUILD:
                    folder = root / 'build/diagnostics/driver_compact_layout' / ('a' * 16)
                    passed = failure != 'layout'
                    receipt(folder, dict(passed=passed, designs={'openlvds_driver_core': dict(
                        passed=passed, drc_count='0' if passed else '1', lvs_passed=True)}))
                elif script == flow.EXTRACT:
                    folder = root / 'build/diagnostics/driver_compact_extraction' / ('b' * 16)
                    receipt(folder, dict(passed=True, rc_audit={'passed': failure != 'rc'}))
                elif script == flow.ASSEMBLE:
                    folder = root / 'build/diagnostics/driver_compact_native_library' / ('c' * 16)
                    receipt(folder, dict(assembly_complete=True))
                elif script == flow.PREPARE:
                    folder = root / 'build/diagnostics/driver_compact_native_pilot' / ('d' * 16)
                    receipt(folder, matrix('native_output_pilot_passed', 6, 3, failure != 'pilot'))
                elif script == flow.FULL and arguments[0] == 'prepare':
                    folder = root / 'build/diagnostics/driver_compact_native' / ('e' * 16)
                    receipt(folder, matrix('native_output_matrix_passed', 30, 15, failure != 'full'))
                if folder is not None:
                    kwargs['stdout'].write('/work/OpenLVDS/' + str(folder.relative_to(root)) + '\n')
                class Result:
                    def check_returncode(self):
                        pass
                return Result()

            with patch.object(flow, 'ROOT', root), patch.object(flow, 'owner', return_value={'MainPID': '0'}), \
                    patch.object(flow, 'source_readiness', return_value='verified-source'), \
                    patch.object(flow.subprocess, 'run', side_effect=child):
                flow.run(out)
                result = json.loads((out / 'summary.json').read_text())
                self.assertFalse(result['qualified_phy'])
                with self.assertRaisesRegex(ValueError, 'Prior'):
                    flow.run(out)
            return commands, result

    def test_failed_source_dispatches_no_physical_work(self):
        commands, result = self.exercise('source')
        self.assertEqual(commands, [])
        self.assertEqual(result['status'], 'held_actual_source_matrix_failed')

    def test_failed_drc_or_lvs_cannot_dispatch_extraction(self):
        commands, result = self.exercise('layout')
        self.assertEqual([s for s, _ in commands], [flow.BUILD])
        self.assertEqual(result['status'], 'held_compensated_layout_failed')

    def test_failed_rc_cannot_dispatch_assembly(self):
        commands, result = self.exercise('rc')
        self.assertEqual([s for s, _ in commands], [flow.BUILD, flow.EXTRACT])
        self.assertEqual(result['status'], 'held_compensated_rc_audit_failed')

    def test_failed_native_pilot_cannot_dispatch_full_matrix(self):
        commands, result = self.exercise('pilot')
        self.assertEqual([s for s, _ in commands], [flow.BUILD, flow.EXTRACT, flow.ASSEMBLE, flow.PREPARE, flow.PILOT])
        self.assertEqual(result['status'], 'held_compensated_native_pilot_failed')

    def test_failed_native_matrix_cannot_report_completed_verification(self):
        commands, result = self.exercise('full')
        self.assertNotIn((flow.FULL, 'verify'), commands)
        self.assertEqual(result['status'], 'held_compensated_native_matrix_failed')

    def test_successful_pipeline_ends_with_independent_full_verification(self):
        commands, result = self.exercise()
        self.assertEqual([s for s, _ in commands], [flow.BUILD, flow.EXTRACT, flow.ASSEMBLE,
            flow.PREPARE, flow.PILOT, flow.FULL, flow.FULL, flow.FULL])
        self.assertEqual(commands[-3:], [(flow.FULL, 'prepare'), (flow.FULL, 'run'), (flow.FULL, 'verify')])
        self.assertEqual(result['status'], 'completed_compensated_native_matrix')
