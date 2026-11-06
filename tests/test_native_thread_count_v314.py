# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_native_thread_count_v314 as probe


class NativeThreadCount(unittest.TestCase):
    def reference(self):
        parent = probe.ROOT / 'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        path = parent / '2/summary.json'
        if not path.exists():
            self.skipTest('requires completed native regular-pair endpoint')
        return json.loads(path.read_text())['result']

    def test_cli_changes_only_explicit_thread_variable(self):
        args = [Path('/loader'), Path('/runtime'), Path('/binary'), Path('/bench.cir'),
                Path('/bench.raw'), Path('/ngspice.log')]
        one = probe.runner.command(*args, 1)
        two = probe.runner.command(*args, 2)
        self.assertEqual([(a, b) for a, b in zip(one, two) if a != b],
                         [('num_threads=1', 'num_threads=2')])
        self.assertIn('-n', one)
        self.assertIn('-b', one)
        for invalid in (0, 3, -1, True, 1.0, '1'):
            with self.subTest(threads=invalid), self.assertRaises(ValueError):
                probe.runner.command(*args, invalid)

    def test_full_original_native_decks_and_endpoint_coverage(self):
        self.assertEqual(probe.plan(), [('1', 1), ('2', 1), ('2', 2)])
        parent = probe.ROOT / 'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        if not (parent / 'manifest.json').exists():
            self.skipTest('requires actual source decks')
        manifest = json.loads((parent / 'manifest.json').read_text())
        for case_id, threads in probe.plan():
            task = manifest['tasks'][int(case_id)]
            spec = task['spec']
            self.assertEqual((spec['process'], spec['temperature'], spec['frequency_mhz']),
                             ('ss', 40, 410))
            self.assertEqual((spec['cycles'], spec['stop_ns'], spec['input_slew_ps'], spec['load_ff']),
                             (8, 25, 100, 20))
            text = (parent / case_id / 'bench.cir').read_text()
            translated, names = probe.runner.original.translate(text)
            self.assertIn('.options klu', translated)
            self.assertIn('.tran 2p 25n 0 2p', translated)
            self.assertIn('reltol=1e-4 abstol=1e-12', translated)
            self.assertGreater(len(names), 1500)
            self.assertEqual(text.count('tanh('), 16)

    def test_actual_reference_parity_and_all_native_terminals_and_controls(self):
        reference = self.reference()
        result = probe.parity(deepcopy(reference), reference)
        self.assertTrue(result['metric_parity_passed'])
        self.assertEqual(result['maximum_timing_difference_ps'], 0)
        self.assertEqual(len(reference['terminal_stress']), 1529)
        self.assertEqual(len(reference['programming_gates']), 173)
        self.assertEqual(len(reference['controls']), 86)
        for cause in ('edge', 'slew', 'missing', 'nan', 'gate', 'peak', 'control', 'terminal_map'):
            changed = deepcopy(reference)
            if cause == 'edge':
                changed['edge_delays_ps']['rise'][0] += .2
            elif cause == 'slew':
                changed['output_slews_10_90_ps']['fall'][0] += .2
            elif cause == 'missing':
                changed['edge_delays_ps']['rise'].pop()
            elif cause == 'nan':
                changed['edge_delays_ps']['rise'][0] = float('nan')
            elif cause == 'gate':
                changed['current_clock_interface_screen_passed'] = False
            elif cause == 'peak':
                changed['terminal_stress'][0]['maximum_terminal_difference_v'] += .002
            elif cause == 'control':
                changed['programming_gates'][0]['maximum_deviation_v'] += .002
            else:
                changed['terminal_stress'][0]['device'] = 'changed_device'
            with self.subTest(cause=cause):
                self.assertFalse(probe.parity(changed, reference)['metric_parity_passed'])

    def test_missing_or_nonfinite_scalar_differences_rejected(self):
        for a, b in (([], []), ([None], [1]), ([float('inf')], [1]),
                     ([1], [1, 2]), ([[1]], [[1]]), (['invalid'], [1])):
            with self.subTest(a=a, b=b):
                self.assertIsNone(probe.vector_difference(a, b))

    def rows(self):
        return [dict(task=dict(source_id=case_id, threads=threads), error=None, result={},
                     parity=dict(metric_parity_passed=True), runtime=dict(
                         configured_threads=threads, active_thread_configuration_observed=True,
                         native_transient_validated=True, wall_seconds=wall))
                for (case_id, threads), wall in zip(probe.plan(), (12., 10., 20.))]

    def test_measured_runtime_requires_all_cases_parity_and_observed_threads(self):
        rows = self.rows()
        result = probe.compare(rows)
        self.assertEqual(result['paired_40_percent_two_over_one_wall_ratio'], 2.)
        self.assertTrue(result['single_thread_faster_on_paired_case'])
        self.assertFalse(result['backend_admitted'])
        self.assertFalse(result['qualified_phy'])
        self.assertIsNone(probe.compare(rows[:2]))
        for field in ('metric_parity_passed', 'active_thread_configuration_observed', 'native_transient_validated'):
            changed = deepcopy(rows)
            target = changed[0]['parity'] if field == 'metric_parity_passed' else changed[0]['runtime']
            target[field] = False
            self.assertFalse(probe.compare(changed)['single_thread_faster_on_paired_case'])
        with self.assertRaisesRegex(ValueError, 'paired'):
            probe.compare(list(reversed(rows)))
        for wall in (0, float('nan'), float('inf')):
            changed = deepcopy(rows)
            changed[1]['runtime']['wall_seconds'] = wall
            with self.assertRaisesRegex(ValueError, 'wall'):
                probe.compare(changed)

    def test_observer_keeps_waiting_and_drains_child_without_termination(self):
        class Child:
            pid = os.getpid()
            count = 0
            def communicate(self, timeout):
                self.count += 1
                if self.count < 3:
                    raise subprocess.TimeoutExpired(['fixture'], timeout)
                return 'native stdout', 'native stderr'
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / 'native.raw'
            raw.write_bytes(b'0' * 65537)
            child = Child()
            stdout, stderr, samples, active = probe.runner.observe(child, raw)
            self.assertEqual((stdout, stderr), ('native stdout', 'native stderr'))
            self.assertEqual(child.count, 3)
            self.assertEqual(sum(samples.values()), 3)
            self.assertEqual(sum(active.values()), 3)

    def test_existing_native_outputs_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            deck = folder / 'bench.cir'
            deck.write_text('fixture\n.print tran V(IN) V(OUT)\n.tran 2p 25n\n.end\n')
            raw = folder / 'bench.raw'
            raw.write_bytes(b'retained native artifact')
            with self.assertRaisesRegex(ValueError, 'Retain'):
                probe.runner.run(deck, folder / 'ngspice.log', 1)
            self.assertEqual(raw.read_bytes(), b'retained native artifact')
            self.assertFalse((folder / 'bench.ngspice.cir').exists())


if __name__ == '__main__':
    unittest.main()
