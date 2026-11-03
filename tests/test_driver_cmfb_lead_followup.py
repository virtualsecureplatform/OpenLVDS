# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_driver_cmfb_lead_source as followup


class CompensationSourceHandoff(unittest.TestCase):
    def test_live_owner_must_match_and_restarts_cannot_trigger_dispatch(self):
        relative = 'build/diagnostics/driver_source_pilot/' + 'a' * 16
        live = dict(MainPID='123', ActiveState='active', InvocationID='first',
            ExecStart='python /work/OpenLVDS/scripts/probe_driver_cmfb_lead.py run /work/OpenLVDS/' + relative)
        followup.admissible_owner(live, relative, False)
        for invalid in [dict(live, ExecStart='other.py'), dict(live, ActiveState='failed'), {'MainPID': '0'}]:
            with self.assertRaises(ValueError):
                followup.admissible_owner(invalid, relative, False)
        followup.admissible_owner({'MainPID': '0'}, relative, True)
        with self.assertRaises(ValueError):
            followup.wait_state(dict(live, MainPID='124', InvocationID='second'), live, True)
        with self.assertRaises(ValueError):
            followup.wait_state({'MainPID': '0'}, live, False)

    def test_prepared_output_must_be_one_content_addressed_campaign(self):
        prefix = '/work/OpenLVDS/build/diagnostics/driver_source_pilot/'
        self.assertEqual(followup.prepared_path(prefix + 'a' * 16, 'driver_source_pilot'),
            'build/diagnostics/driver_source_pilot/' + 'a' * 16)
        for invalid in [prefix + '../driver_shape_source/' + 'a' * 16,
                prefix + 'not-an-identity', prefix + 'a' * 16 + '/nested', 'relative/path']:
            with self.assertRaises(ValueError):
                followup.prepared_path(invalid, 'driver_source_pilot')

    def exercise(self, diagnostic_pass=True, pilot_pass=True, full_pass=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagnostic = root / 'build/diagnostics/driver_source_pilot' / ('d' * 16)
            pilot = root / 'build/diagnostics/driver_source_pilot' / ('a' * 16)
            full = root / 'build/diagnostics/driver_shape_source' / ('b' * 16)

            def receipt(folder, stage, passed):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'manifest.json').write_text('{}')
                n, p, flag = (6, 3, 'source_pilot_passed') if stage == 'pilot' else (30, 15, 'source_waveform_matrix_passed')
                (folder / 'summary.json').write_text(json.dumps({flag: passed,
                    'required_cases': n, 'required_pvt': p, 'passed_pvt': p if passed else 0,
                    'manifest_sha256': followup.sha(folder / 'manifest.json')}))

            receipt(diagnostic, 'pilot', diagnostic_pass)
            expected_owner = dict(MainPID='123', InvocationID='first')
            identity = dict(source=str(diagnostic.relative_to(root)), original='original',
                owner=expected_owner, unit='diagnostic.service', inputs={})
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            out = root / 'build/diagnostics' / followup.NAMESPACE / digest
            out.mkdir(parents=True)
            (out / 'manifest.json').write_text(json.dumps({'identity': identity}))
            commands = []

            def child(args, **kwargs):
                action = args[4]
                commands.append(action)
                if action == 'prepare-pilot':
                    receipt(pilot, 'pilot', pilot_pass)
                    kwargs['stdout'].write('/work/OpenLVDS/' + str(pilot.relative_to(root)) + '\n')
                elif action == 'prepare-full':
                    receipt(full, 'full', full_pass)
                    kwargs['stdout'].write('/work/OpenLVDS/' + str(full.relative_to(root)) + '\n')
                class Result:
                    def check_returncode(self):
                        pass
                return Result()

            with patch.object(followup, 'ROOT', root), patch.object(followup, 'owner',
                    return_value={'MainPID': '0'}), patch.object(followup.subprocess, 'run', side_effect=child):
                followup.run(out)
                report = json.loads((out / 'summary.json').read_text())
                self.assertFalse(report['qualified_phy'])
                with self.assertRaisesRegex(ValueError, 'Prior'):
                    followup.run(out)
            return commands, report

    def test_failed_diagnostic_dispatches_nothing(self):
        commands, report = self.exercise(diagnostic_pass=False)
        self.assertEqual(commands, [])
        self.assertEqual(report['status'], 'held_compensation_diagnostic_failed')

    def test_failed_actual_pilot_cannot_dispatch_full_matrix(self):
        commands, report = self.exercise(pilot_pass=False)
        self.assertEqual(commands, ['prepare-pilot', 'run'])
        self.assertEqual(report['status'], 'held_actual_source_pilot_failed')

    def test_failed_full_matrix_cannot_produce_readiness(self):
        commands, report = self.exercise(full_pass=False)
        self.assertEqual(commands, ['prepare-pilot', 'run', 'prepare-full', 'run'])
        self.assertFalse(report['source_waveform_matrix_passed'])

    def test_successful_order_requires_final_independent_verification(self):
        commands, report = self.exercise()
        self.assertEqual(commands, ['prepare-pilot', 'run', 'prepare-full', 'run', 'verify'])
        self.assertTrue(report['source_waveform_matrix_passed'])
        self.assertEqual(report['status'], 'completed_actual_source_matrix')
