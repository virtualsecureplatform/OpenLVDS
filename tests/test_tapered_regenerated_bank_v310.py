# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_tapered_regenerated_bank_v310 as probe
import run_tapered_regenerated_followup_v311 as followup


class TaperedRegeneratedBank(unittest.TestCase):
    def test_complete_eight_case_grid_and_original_fixture(self):
        specs = probe.specifications()
        self.assertEqual(len(specs), 8)
        observations = {v: dict(devices=[], controls=[]) for v in probe.MODELS}
        identity = dict(model='native.lib', ports=['IN', 'OUT', 'VPWR', 'VGND'],
                        observations=observations)
        for variant in probe.MODELS:
            group = [s for s in specs if s['first_restorer'] == variant]
            self.assertEqual([(s['coarse'], s['fine'], s['duty']) for s in group],
                             [(0, 0, .5), (0, 31, .6), (0, 31, .4), (1, 0, .5)])
            for spec in group:
                self.assertEqual((spec['process'], spec['temperature'], spec['frequency_mhz']),
                                 ('ss', 40, 410))
                text = probe.fixture(Path('/unused'), identity, spec)
                original = probe.source.fixture(Path('/unused') / variant,
                                                dict(identity, observations=observations[variant]), spec)
                self.assertEqual(text, original.replace(probe.source.TOP, probe.TOP)
                                 .replace('OpenLVDS ' + probe.source.VERSION,
                                          'OpenLVDS ' + probe.VERSION))
                self.assertEqual(text.count('tanh('), 16)
                self.assertIn('.tran 2p 25n 0 2p', text)
                self.assertIn('V(XD:restored_b)', text)
                self.assertIn('VDD VDD 0 1.8', text)

    def actual_materials(self):
        parent = probe.ROOT / 'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        rc = probe.ROOT / 'build/diagnostics/tapered_fine_driver_rc_v309/4cf2d31774fd60cd'
        if not (parent / 'manifest.json').exists() or not (rc / 'summary.json').exists():
            self.skipTest('requires actual native source bank and qualified smaller-cell RC')
        previous = json.loads((parent / 'manifest.json').read_text())['identity']['observations']
        report = json.loads((rc / 'summary.json').read_text())
        cells = {v: probe.cell_definition((probe.ROOT / row['extraction']['netlist']).read_text(),
                                          probe.MODELS[v])
                 for v, row in zip(probe.MODELS, report['rows'])}
        return (parent / 'bank.spice').read_text(), previous, cells

    def test_actual_native_replacement_preserves_other_terminals_controls_and_final_driver(self):
        bank, previous, cells = self.actual_materials()
        for variant in probe.MODELS:
            result, observations, proof = probe.transform(bank, previous, cells[variant], variant)
            self.assertEqual(len(observations['devices']), probe.COUNTS[variant])
            self.assertEqual(observations['controls'], previous['controls'])
            self.assertEqual(observations['programming_gates'], previous['programming_gates'])
            self.assertEqual(proof['native_mims'], 43)
            self.assertFalse(proof['qualified_phy'])
            calls = [w for w in probe.source.native.definitions(result)[probe.TOP][1]
                     if w[0].startswith('Xfine_regenerate')]
            self.assertEqual(calls, [
                ['Xfine_regenerate0', 'fine_node', 'restored_b', 'VGND', 'VPWR', probe.MODELS[variant]],
                ['Xfine_regenerate1', 'restored_b', 'OUT', 'VGND', 'VPWR', probe.source.MODEL]])
            old = {d['name']: d for d in previous['devices']
                   if not d['name'].startswith('XD:Xfine_regenerate0:')}
            new = {d['name']: d for d in observations['devices'] if d['name'] in old}
            self.assertEqual(old, new)

    def test_wrong_size_ports_and_unrelated_terminal_corruption_rejected(self):
        bank, previous, cells = self.actual_materials()
        with self.assertRaisesRegex(ValueError, 'port order'):
            probe.transform(bank, previous, cells['p6n4'].replace(' A Y VGND VPWR',
                                                               ' Y A VGND VPWR', 1), 'p6n4')
        with self.assertRaisesRegex(ValueError, 'namespace'):
            probe.transform(bank, previous, cells['p10n8'], 'p6n4')
        bad = deepcopy(previous)
        index = next(k for k, d in enumerate(bad['devices'])
                     if not d['name'].startswith('XD:Xfine_regenerate0:'))
        bad['devices'][index]['terminals'][0] = 'unexpected_terminal'
        with self.assertRaisesRegex(ValueError, 'terminal maps'):
            probe.transform(bank, bad, cells['p6n4'], 'p6n4')
        with self.assertRaisesRegex(ValueError, 'topology'):
            probe.transform(bank.replace('Xfine_regenerate1 restored_b OUT',
                                         'Xfine_regenerate1 fine_node OUT', 1),
                            previous, cells['p6n4'], 'p6n4')

    def test_actual_qualified_driver_materials_and_hashes_verified(self):
        parent = probe.ROOT / 'build/diagnostics/tapered_fine_driver_rc_v309/4cf2d31774fd60cd'
        if not (parent / 'summary.json').exists():
            self.skipTest('requires actual qualified tapered-driver RC')
        cells, paths, identity = probe.driver_materials(parent)
        self.assertEqual(list(cells), list(probe.MODELS))
        self.assertEqual(identity['version'], 'tapered-restorer-regular-pn-driver-native-distributed-rc-v309.1')
        self.assertIn(parent / 'manifest.json', paths)
        for variant, model in probe.MODELS.items():
            self.assertEqual(set(probe.source.native.definitions(cells[variant])), {model})

    def test_continuation_follows_exact_live_owner_and_rejects_restart(self):
        invocation = '1' * 32
        info = dict(InvocationID=invocation, MainPID=str(os.getpid()), ActiveState='active')
        self.assertFalse(followup.ready(info, invocation, False))
        self.assertTrue(followup.ready(info, invocation, True))
        for completed in (False, True):
            with self.assertRaisesRegex(ValueError, 'invocation changed'):
                followup.ready(dict(info, InvocationID='2' * 32), invocation, completed)
        with self.assertRaisesRegex(ValueError, 'exact'):
            followup.ready(info, '', False)

    def test_missing_owner_without_completed_receipt_never_advances(self):
        invocation = '1' * 32
        terminal = dict(InvocationID='', MainPID='0', ActiveState='inactive')
        with self.assertRaises(ValueError):
            followup.ready(terminal, invocation, False)
        self.assertTrue(followup.ready(terminal, invocation, True))

    def rows(self):
        rows = []
        for spec in probe.specifications():
            delay = {(0, 0): 500, (0, 31): 850, (1, 0): 700}[spec['coarse'], spec['fine']]
            rows.append(dict(spec=spec, error=None, result=dict(
                current_clock_interface_screen_passed=True, zero_code_fast_quarter_headroom_ps=100,
                edge_delays_ps={e: [delay + k * .1 for k in range(8)] for e in ('rise', 'fall')})))
        return rows

    def test_every_native_gate_all_eight_edges_and_both_overlaps_required(self):
        rows = self.rows()
        result = probe.compare(rows)
        self.assertTrue(all(r['component_hypothesis_passed'] for r in result['variants'].values()))
        self.assertFalse(result['electrical_qualification_passed'])
        self.assertIsNone(probe.compare(rows[:7]))
        for variant_index, variant in enumerate(probe.MODELS):
            start = variant_index * 4
            for cause in ('gate', 'missing', 'nonfinite', 'negative', 'overlap'):
                changed = deepcopy(rows)
                if cause == 'gate':
                    changed[start]['result']['current_clock_interface_screen_passed'] = False
                elif cause == 'missing':
                    changed[start]['result']['edge_delays_ps']['fall'].pop()
                elif cause == 'nonfinite':
                    changed[start]['result']['edge_delays_ps']['rise'][0] = float('nan')
                elif cause == 'negative':
                    changed[start]['result']['edge_delays_ps']['rise'][0] = -1
                else:
                    changed[start+3]['result']['edge_delays_ps']['fall'][-1] = 900
                with self.subTest(variant=variant, cause=cause):
                    self.assertFalse(probe.compare(changed)['variants'][variant]['component_hypothesis_passed'])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            probe.compare(list(reversed(rows)))

    def test_incomplete_baseline_never_reaches_driver_preparation_or_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            with patch.object(probe.source, 'bound') as bound:
                with self.assertRaisesRegex(ValueError, 'naturally completed'):
                    probe.prepare(parent, Path('/unused'))
                bound.assert_not_called()

    def test_complete_baseline_requires_replayed_isolated_latency_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            case = parent / '0'
            case.mkdir()
            files = {}
            for name in ('bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'):
                (case / name).write_text('fixture')
                files[name] = probe.sha(case / name)
            gates = ('all_input_output_pulses_present', 'input_timing_stimulus_passed',
                     'full_swing_pulses_passed', 'unwrapped_native_epoch_passed',
                     'pulse_order_and_widths_passed', 'period_screen_passed',
                     'repeated_delay_screen_passed', 'terminal_screen_passed',
                     'control_settling_passed', 'current_downstream_250ps_slew_domain_passed')
            result = dict.fromkeys(gates, True)
            result['zero_code_quarter_passed'] = False
            task = dict(id='0', spec=probe.source.specifications()[0])
            row = dict(task=task, spec=task['spec'], result=result, error=None, files=files)
            manifest = dict(tasks=[task], identity={})
            (case / 'summary.json').write_text(json.dumps(row))
            with patch.object(probe.source, 'measure', return_value=result):
                self.assertEqual(probe.require_baseline(parent, manifest)[0], row)
            for gate in (*gates, 'zero_code_quarter_passed'):
                changed = dict(result, **{gate: not result[gate]})
                with patch.object(probe.source, 'measure', return_value=changed):
                    with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, 'isolated'):
                        probe.require_baseline(parent, manifest)


if __name__ == '__main__':
    unittest.main()
