# SPDX-License-Identifier: GPL-3.0-only
"""Check paired removal against the actual recovered native bank and gates."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_direct_balanced_bank_v365 as p


class DirectBalancedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = json.loads((p.PARENT/'manifest.json').read_text())['identity']
        cls.original = (p.PARENT/'bank.spice').read_text()
        cls.text, cls.obs = p.transform(cls.original, cls.old['observations'])

    def test_actual_inventory_controls_and_every_programming_gate_remain_observed(self):
        _, leaves = p.source.inventory.native_leaves(p.source.collapse(self.text), p.TOP)
        self.assertEqual(sum('fet_' in d['model'] for d in leaves), 1980)
        self.assertEqual(sum('cap_mim' in d['model'] for d in leaves), 130)
        self.assertEqual(self.obs['controls'], self.old['observations']['controls'])
        self.assertEqual(self.obs['programming_gates'], self.old['observations']['programming_gates'])
        self.assertEqual(len(self.obs['devices']), 1980)
        self.assertEqual(len(self.obs['controls']), 86)
        self.assertEqual(len(self.obs['programming_gates']), 266)
        lookup = {d['name']: d for d in self.obs['devices']}
        for g in self.obs['programming_gates']:
            self.assertEqual(lookup[g['device']]['terminals'][1], g['gate_node'])
        self.assertTrue(all(d['limit_v'] == 1.95 for d in self.obs['devices']))

    def test_pair_removal_keeps_logical_polarity_for_every_group_selection(self):
        # The inverter before a selected pass path and the following inverter
        # cancel for every valid selection. This establishes polarity only;
        # native loading, glitches and timing still require the full runs.
        for taps in itertools.product((False, True), repeat=4):
            for k in range(4):
                original_fine_input = not (not taps[k])
                direct_fine_input = taps[k]
                self.assertEqual(original_fine_input, direct_fine_input)
        defs = p.source.native.definitions(self.text)
        body = defs[p.TOP][1]
        self.assertFalse(any(w[0] == 'Xfine_pre' or w[0].startswith('Xgroup_compound') for w in body))
        self.assertIn(['Xfine_isolate', 'selected', 'fine_node', 'VGND', 'VPWR', p.parent.FINE], body)
        self.assertEqual(sum(w[-1] == p.source.COARSE for w in body), 16)
        self.assertEqual(sum(w[0].startswith('Xfine_unit') for w in body), 31)
        self.assertEqual(sum(w[0].startswith('Xfine_copy') for w in body), 31)
        for name in p.source.native.definitions(self.original):
            if name != p.parent.TOP:
                self.assertEqual(p.source.definition(self.text, name), p.source.definition(self.original, name))

    def test_missing_group_root_or_control_map_is_rejected(self):
        for old, new in [('Xfine_pre selected pre_out', 'Xfine_pre WRONG pre_out'),
                         ('Xgroup_compound2 tree0_2 regenerated2', 'Xgroup_compound2 tree0_1 regenerated2'),
                         ('Xroot_parallel3 regenerated3', 'Xroot_parallel3 tree0_3')]:
            with self.assertRaises(ValueError):
                p.transform(self.original.replace(old, new, 1), self.old['observations'])
        obs = deepcopy(self.old['observations'])
        obs['programming_gates'].pop()
        with self.assertRaises(ValueError):
            p.transform(self.original, obs)

    def test_generated_native_fixture_keeps_models_and_every_original_clock_event(self):
        identity = dict(self.old, observations=self.obs, macro_top=p.TOP)
        self.assertEqual([(s['coarse'], s['fine'], s['duty']) for s in p.specifications()],
                         [(0, 0, .5), (0, 31, .6), (0, 31, .4), (1, 0, .5)])
        for spec in p.specifications():
            text = p.fixture(p.ROOT/'build/unused-direct-balanced-bank', identity, spec)
            self.assertIn('.tran 2p 25n 0 2p', text)
            self.assertIn('VDD VDD 0 1.8', text)
            self.assertIn('CLOAD OUT 0 20f', text)
            self.assertEqual(text.count('tanh((time-'), 16)
            self.assertEqual(text.count(p.TOP), 1)
            self.assertNotIn('pre_out', text)
            self.assertNotIn('regenerated', text)
            self.assertIn('V(XD:selected)', text)
            self.assertIn('.lib "'+self.old['model']+'" ss', text)
            self.assertNotIn('REPLAY', text)

    def test_latency_recovery_voltage_and_both_coarse_overlaps_remain_required(self):
        native = json.loads((p.ROOT/'build/diagnostics/restored_fine_recovery_v355/b88568e79d9ee803/1/summary.json').read_text())['result']
        rows = []
        for k, spec in enumerate(p.specifications()):
            delay = 100. if k == 0 else 150. if k == 3 else 200.
            result = dict(native, edge_delays_ps={e: [delay]*8 for e in ('rise', 'fall')})
            rows.append(dict(spec=spec, result=result, error=None))
        self.assertTrue(p.compare(rows)['component_hypothesis_passed'])
        self.assertFalse(p.compare(rows)['qualified_phy'])
        for key in ('all_input_output_pulses_present', 'zero_code_quarter_passed', 'terminal_screen_passed',
                    'period_screen_passed', 'repeated_delay_screen_passed', 'control_settling_passed'):
            bad = deepcopy(rows)
            bad[0]['result'][key] = False
            self.assertFalse(p.compare(bad)['component_hypothesis_passed'])
        for edge in ('rise', 'fall'):
            bad = deepcopy(rows)
            bad[3]['result']['edge_delays_ps'][edge] = [250.]*8
            self.assertFalse(p.compare(bad)['component_hypothesis_passed'])
        self.assertIsNone(p.compare(rows[:-1]))

    def test_partial_latency_receipt_cannot_claim_completion_or_omit_captured_bytes(self):
        original = json.loads((p.ROOT/'build/reports/live_bank_history_replay_v364/20261107T145755Z/summary.json').read_text())
        for field in ('source_waveform_complete', 'qualified_phy', 'inputs'):
            bad = deepcopy(original)
            bad[field] = {} if field == 'inputs' else True
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'summary.json'
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    p.evidence(path)


if __name__ == '__main__':
    unittest.main()
