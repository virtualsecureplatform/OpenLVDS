# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_request_taper_counter_v317 as probe
import run_native_binary_v2 as runner


class RequestTaperCounterTests(unittest.TestCase):
    def material(self):
        parent = probe.ROOT / 'build/diagnostics/counter_matched_buffers_v306/f9b748a6ac5c2ee2'
        drivers = probe.ROOT / 'build/diagnostics/tapered_fine_driver_rc_v309/4cf2d31774fd60cd'
        if not all((p / 'manifest.json').exists() for p in (parent, drivers)):
            self.skipTest('Requires actual matched-counter and qualified small-driver artifacts')
        manifest = json.loads((parent / 'manifest.json').read_text())
        report = json.loads((drivers / 'summary.json').read_text())
        row = next(r for r in report['rows'] if r['macro'] == probe.SMALL)
        small = probe.source.cell_definition((probe.ROOT / row['extraction']['netlist']).read_text(), probe.SMALL)
        return parent, manifest, (parent / 'matched/cells.spice').read_text(), (parent / 'matched/pair.spice').read_text(), small

    def test_actual_request_only_graph_maps_and_qualified_component_bytes(self):
        parent, manifest, cells, module, small = self.material()
        previous = manifest['identity']['devices']['matched']
        new, retained, devices, proof = probe.transform(cells, module, previous, small)
        self.assertEqual(retained, module)
        self.assertEqual(len(devices), 808)
        self.assertEqual(proof['removed_request_first_stage_mos'], 72)
        self.assertEqual(proof['added_request_first_stage_mos'], 36)
        self.assertGreater(proof['native_mims'], 0)
        self.assertFalse(proof['shared_wire_rc_qualified'])
        definitions = probe.source.source.native.definitions(new)
        self.assertEqual(definitions[probe.BUFFER][1], [
            ['Xrestore0', 'A', 'internal_b', 'VGND', 'VPWR', probe.SMALL],
            ['Xrestore1', 'internal_b', 'X', 'VGND', 'VPWR', probe.source.PN]])
        for role in probe.source.ROLES:
            call = next(w for w in definitions[probe.source.CORE][1] if w[0] == 'X' + role)
            self.assertEqual(call[-1], probe.BUFFER if role in probe.REQUEST_ROLES else probe.source.BUFFER)
        for name in probe.source.source.native.definitions(cells):
            if name != probe.source.CORE:
                self.assertEqual(probe.source.cell_definition(cells, name), probe.source.cell_definition(new, name))
        self.assertEqual(probe.source.cell_definition(new, probe.SMALL), small)
        by_name = {d['name']: d for d in devices}
        for device in previous:
            if not device['name'].startswith(probe.PREFIXES):
                self.assertEqual(by_name[device['name']], device)

    def test_changed_supply_role_ports_namespace_and_unrelated_maps_rejected(self):
        parent, manifest, cells, module, small = self.material()
        previous = manifest['identity']['devices']['matched']
        cases = [
            (cells.replace('Xrequest_driver REQUEST request_i VGND VPWR',
                           'Xrequest_driver REQUEST request_i VPWR VGND', 1), small),
            (cells.replace('Xrestore0 A internal_b VGND VPWR ' + probe.source.PN,
                           'Xrestore0 A internal_b VGND VPWR invalid_driver', 1), small),
            (cells, small.replace('.subckt ' + probe.SMALL + ' A Y VGND VPWR',
                                  '.subckt ' + probe.SMALL + ' Y A VGND VPWR', 1)),
            (cells + '\n' + small, small)]
        for text, component in cases:
            with self.assertRaises(ValueError):
                probe.transform(text, module, previous, component)
        bad = deepcopy(previous)
        next(d for d in bad if not d['name'].startswith(probe.PREFIXES))['terminals'][0] += '_changed'
        with self.assertRaisesRegex(ValueError, 'native terminals'):
            probe.transform(cells, module, bad, small)

    def test_four_original_full_native_fixtures_keep_twenty_ps_request(self):
        parent, manifest, cells, module, small = self.material()
        _, _, devices, _ = probe.transform(cells, module, manifest['identity']['devices']['matched'], small)
        self.assertEqual([(s['temperature'], s['duty'], s['stop_level']) for s in probe.specifications()],
                         [(0, .6, 0), (0, .6, 1), (40, .6, 0), (40, .6, 1)])
        for spec in probe.specifications():
            text = probe.fixture(Path('/unused'), spec, devices)
            self.assertEqual(text.replace('OpenLVDS ' + probe.VERSION, 'OpenLVDS ' + probe.source.VERSION, 1),
                             probe.source.fixture(Path('/unused'), spec, devices))
            self.assertIn('.tran 1p 26n 0 1p', text)
            self.assertIn('3.39n 0 3.41n 1.8', text)
            self.assertIn('22.99n 0 23.01n 1.8', text)
            self.assertIn('VDD VDD 0 1.8', text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12', text)
            _, names = runner.translate(text)
            self.assertEqual(len(names), len(set(names)))
            for device in devices:
                for terminal in device['terminals']:
                    if terminal != '0':
                        self.assertIn('v(' + terminal.replace(':', '.').lower() + ')', names)

    def test_original_pair_requires_isolated_stress_failure_and_timing_gain(self):
        parent, manifest, cells, module, small = self.material()
        rows = [json.loads((parent / str(k) / 'summary.json').read_text()) for k in (0, 1)]
        probe.validate_pair(rows)
        for key in ('terminal_screen_passed', 'phase_arming_passed', 'hypothesis_point_checks_passed'):
            bad = deepcopy(rows)
            bad[1]['result'][key] = not bad[1]['result'][key]
            with self.assertRaises(ValueError):
                probe.validate_pair(bad)
        with self.assertRaises(ValueError):
            probe.validate_pair(rows[:1])

    def test_full_actual_cause_reproduces_eighty_exact_failed_terminal_samples(self):
        parent, manifest, cells, module, small = self.material()
        evidence = probe.ROOT / 'build/reports/matched_counter_stress/20261106T232941Z'
        rows, paths = probe.require_cause(parent, manifest, evidence)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]['result']['hypothesis_point_checks_passed'])
        self.assertFalse(rows[1]['result']['terminal_screen_passed'])
        self.assertIn(evidence / 'summary.json', paths)

    def test_all_four_results_and_original_safety_and_low_window_gates_required(self):
        rows = [dict(task=dict(id=str(k), spec=s), error=None, result=dict(
            hypothesis_point_checks_passed=True, counter_feasibility_passed=True, terminal_screen_passed=True,
            minimum_clock_low_voltage_margin_v=.1,
            low_windows=dict(all_three_assertions_in_original_low_windows=True, minimum_remaining_low_window_ps=100)))
            for k, s in enumerate(probe.specifications())]
        result = probe.assess(rows)
        self.assertTrue(result['request_taper_component_hypothesis_passed'])
        self.assertFalse(result['qualified_phy'])
        self.assertFalse(result['whole_clock_rc_qualified'])
        self.assertIsNone(probe.assess(rows[:3]))
        for field in ('hypothesis_point_checks_passed', 'counter_feasibility_passed', 'terminal_screen_passed'):
            bad = deepcopy(rows); bad[0]['result'][field] = False
            self.assertFalse(probe.assess(bad)['request_taper_component_hypothesis_passed'])
        for value in (0., -1., float('nan')):
            bad = deepcopy(rows); bad[0]['result']['low_windows']['minimum_remaining_low_window_ps'] = value
            self.assertFalse(probe.assess(bad)['request_taper_component_hypothesis_passed'])
        bad = deepcopy(rows); bad[0]['error'] = 'native error'
        self.assertIsNone(probe.assess(bad))
        with self.assertRaises(ValueError):
            probe.assess(list(reversed(rows)))

    def test_only_historical_native_raw_is_deferred_and_guard_set_is_exact(self):
        inputs = {'build/diagnostics/a/0/bench.raw': 'raw', 'scripts/x.py': 'code',
                  'build/tools/runtime.so': 'binary', 'models/input.raw': 'source',
                  'build/diagnostics/a/summary.json': 'proof', 'cells.spice': 'circuit'}
        self.assertEqual(probe.guard_inputs(inputs), {k: v for k, v in inputs.items() if k != 'build/diagnostics/a/0/bench.raw'})

    def test_existing_running_or_failed_state_cannot_be_restarted_or_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for status in ('running', 'failed', 'complete'):
                original = json.dumps(dict(status=status))
                (folder / 'state.json').write_text(original)
                with patch.object(probe, 'bound') as bound, self.assertRaisesRegex(ValueError, 'Retain previous'):
                    probe.run(folder)
                bound.assert_not_called()
                self.assertEqual((folder / 'state.json').read_text(), original)

    def test_prepared_identity_canonical_library_hashes_guards_and_native_decks(self):
        folder = probe.ROOT / 'build/diagnostics/request_taper_counter_v317/a9021aae03b1ad1c'
        if not (folder / 'manifest.json').exists():
            self.skipTest('Requires actual prepared REQUEST taper context')
        manifest = probe.bound(folder, full=False)
        identity = manifest['identity']
        self.assertEqual(len(identity['devices'][probe.VARIANT]), 808)
        self.assertEqual(identity['native_revision']['native_mims'], 56)
        self.assertEqual(manifest['libraries'], identity['library_sha256'])
        self.assertEqual(len(identity['inputs']), 2899)
        self.assertEqual(len(identity['guards']), 2798)
        self.assertEqual(identity['guards'], probe.guard_inputs(identity['inputs']))
        self.assertEqual(identity['max_workers'], 1)
        self.assertEqual(identity['priority'], 1)
        self.assertEqual(len(manifest['tasks']), 4)
        for name, expected in identity['library_sha256'].items():
            self.assertEqual(probe.sha(folder / name), expected)
        # An updated outer checksum cannot legitimize a changed generated
        # library: its checksum also belongs to the canonical identity.
        changed = deepcopy(manifest)
        changed['libraries']['cells.spice'] = '0' * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / 'build/diagnostics' / probe.CONTEXT / folder.name
            copied.mkdir(parents=True)
            (copied / 'manifest.json').write_text(json.dumps(changed))
            with patch.object(probe, 'ROOT', root), patch.object(probe, 'provenance') as provenance:
                with self.assertRaisesRegex(ValueError, 'native context changed'):
                    probe.bound(copied, full=False)
                provenance.assert_not_called()


if __name__ == '__main__':
    unittest.main()
