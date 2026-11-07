# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_numeric_native_threads_v319 as probe


class NumericNativeThreadsTests(unittest.TestCase):
    def audit(self):
        folder = probe.ROOT / 'build/reports/numeric_thread_startup_v318/20261107T000751Z'
        if not (folder / 'summary.json').exists():
            self.skipTest('Requires exact source/host/private-startup audit')
        return folder

    def test_actual_audit_binds_official_source_host_workers_and_private_frontends(self):
        folder = self.audit()
        paths = probe.require_audit(folder)
        self.assertIn(folder / 'summary.json', paths)
        for count in (1, 2):
            self.assertIn(folder / str(count) / probe.runner.INIT_DIRECTORY / '.spiceinit', paths)

    def test_changed_audit_flags_workers_or_frontend_results_are_rejected(self):
        folder = self.audit()
        original = json.loads((folder / 'summary.json').read_text())
        cases = []
        for key in ('qualified_phy', 'backend_admitted', 'full_native_numeric_thread_configuration_verified'):
            changed = deepcopy(original); changed[key] = True; cases.append(changed)
        changed = deepcopy(original); changed['legacy_process']['actual_threads'] = 1; cases.append(changed)
        changed = deepcopy(original); changed['legacy_process']['positive_native_progress_observed'] = False; cases.append(changed)
        changed = deepcopy(original); changed['frontend_checks']['1']['private_startup_loaded'] = False; cases.append(changed)
        read = Path.read_text
        for changed in cases:
            def text(path, *args, **kwargs):
                return json.dumps(changed) if path == folder / 'summary.json' else read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', text), self.assertRaises(ValueError):
                probe.require_audit(folder)

    def test_native_plan_and_translated_circuit_are_exactly_original(self):
        parent = probe.ROOT / 'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        if not (parent / 'manifest.json').exists():
            self.skipTest('Requires completed original native endpoint fixtures')
        self.assertEqual(probe.plan(), [('1', 1), ('2', 1), ('2', 2)])
        for case_id in ('1', '2'):
            row = json.loads((parent / case_id / 'summary.json').read_text())
            translated, names = probe.runner.original.translate((parent / case_id / 'bench.cir').read_text())
            self.assertEqual(hashlib.sha256(translated.encode()).hexdigest(), row['files']['bench.ngspice.cir'])
            self.assertEqual(len(names), len(set(names)))
            self.assertIn('.tran 2p 25n 0 2p', translated)

    def rows(self):
        return [dict(task=dict(source_id=case_id, threads=threads), result={}, error=None,
            parity=dict(metric_parity_passed=True), runtime=dict(configured_threads=threads,
                active_thread_configuration_observed=True, native_transient_validated=True,
                private_numeric_thread_init_loaded=True, private_numeric_thread_init_unchanged=True,
                original_deck_translation_retained=True, pinned_runtime_verified=True,
                models_or_tolerances_changed=False, wall_seconds=[3., 2., 4.][k]))
                for k, (case_id, threads) in enumerate(probe.plan())]

    def test_speed_result_requires_native_parity_actual_workers_and_verified_initialization(self):
        rows = self.rows(); result = probe.compare(rows)
        self.assertTrue(result['single_thread_faster_on_paired_case'])
        self.assertEqual(result['paired_40_percent_two_over_one_wall_ratio'], 2.)
        self.assertFalse(result['backend_admitted'])
        self.assertFalse(result['qualified_phy'])
        for field in ('active_thread_configuration_observed', 'native_transient_validated',
                      'private_numeric_thread_init_loaded', 'private_numeric_thread_init_unchanged',
                      'original_deck_translation_retained', 'pinned_runtime_verified'):
            bad = deepcopy(rows); bad[0]['runtime'][field] = False
            result = probe.compare(bad)
            self.assertFalse(result['single_thread_faster_on_paired_case'])
            self.assertIsNone(result['paired_40_percent_two_over_one_wall_ratio'])
        bad = deepcopy(rows); bad[0]['runtime']['models_or_tolerances_changed'] = True
        self.assertFalse(probe.compare(bad)['single_thread_faster_on_paired_case'])
        bad = deepcopy(rows); bad[1]['parity']['metric_parity_passed'] = False
        self.assertIsNone(probe.compare(bad)['paired_40_percent_two_over_one_wall_ratio'])
        self.assertIsNone(probe.compare(rows[:2]))
        with self.assertRaises(ValueError):
            probe.compare(list(reversed(rows)))

    def test_all_non_raw_inputs_including_private_init_and_runtime_are_guarded(self):
        inputs = {'build/diagnostics/old/0/bench.raw': 'history', 'models/input.raw': 'model',
                  'audit/1/thread-init-v318/.spiceinit': 'init', 'build/tools/runtime.so': 'runtime',
                  'source.tar.gz': 'source', 'scripts/runner.py': 'code'}
        self.assertEqual(probe.guarded_inputs(inputs), {k: v for k, v in inputs.items()
                                                       if k != 'build/diagnostics/old/0/bench.raw'})

    def test_prior_state_is_retained_without_native_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); original = '{"status":"running"}'
            (folder / 'state.json').write_text(original)
            with patch.object(probe, 'bound') as bound, self.assertRaisesRegex(ValueError, 'Retain previous'):
                probe.run(folder)
            bound.assert_not_called()
            self.assertEqual((folder / 'state.json').read_text(), original)

    def test_prepared_context_binds_recipes_original_translation_and_all_guards(self):
        folder = probe.ROOT / 'build/diagnostics/numeric_native_threads_v319/3d8fb25e4ae0db0e'
        if not (folder / 'manifest.json').exists():
            self.skipTest('Requires actual prepared numeric-thread native context')
        manifest = probe.bound(folder, full=False)
        identity = manifest['identity']
        self.assertEqual(len(identity['inputs']), 2429)
        self.assertEqual(len(identity['guarded_inputs']), 2335)
        self.assertEqual(identity['guarded_inputs'], probe.guarded_inputs(identity['inputs']))
        self.assertEqual(identity['max_workers'], 1)
        self.assertEqual(identity['priority'], 2)
        self.assertFalse(manifest['backend_admitted'])
        self.assertFalse(manifest['qualified_phy'])
        self.assertEqual(identity['initialization_recipes'], {str(n): probe.runner.startup_text(n) for n in (1, 2)})
        for task in manifest['tasks']:
            original = probe.ROOT / identity['parent'] / task['source_id'] / 'bench.cir'
            self.assertEqual((folder / task['id'] / 'bench.cir').read_bytes(), original.read_bytes())
            self.assertEqual(identity['translations'][task['source_id']],
                             identity['references'][task['source_id']]['row']['files']['bench.ngspice.cir'])


if __name__ == '__main__':
    unittest.main()
