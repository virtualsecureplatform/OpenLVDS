# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_preconditioned_fine_bank_v315 as probe
import run_native_binary_v2 as runner


class PreconditionedFineBank(unittest.TestCase):
    def material(self):
        parent = probe.ROOT/'build/diagnostics/tapered_regenerated_bank_v310/c10259773d77c082'
        if not (parent/'manifest.json').exists():
            self.skipTest('requires actual qualified post-fine taper assembly')
        identity = json.loads((parent/'manifest.json').read_text())['identity']
        return (parent/'p10n8/bank.spice').read_text(), identity['observations']['p10n8'], identity

    def test_actual_native_graph_polarity_components_and_other_terminals(self):
        bank, old, identity = self.material()
        result, observations, proof = probe.transform(bank, old)
        self.assertEqual(len(observations['devices']), 1511)
        self.assertEqual(proof['native_mims'], 43)
        self.assertEqual(observations['programming_gates'], old['programming_gates'])
        self.assertEqual(observations['controls'], old['controls'])
        definitions = probe.source.native.definitions(result)
        self.assertFalse(any('restored_b' in words for words in definitions[probe.TOP][1]))
        calls = {w[0]: w for w in definitions[probe.TOP][1] if w[0].startswith('Xfine_')}
        self.assertEqual(calls['Xfine_regenerate0'],
                         ['Xfine_regenerate0', 'selected', 'conditioned', 'VGND', 'VPWR', probe.SMALL])
        self.assertEqual(calls['Xfine_isolate'],
                         ['Xfine_isolate', 'conditioned', 'fine_node', 'VGND', 'VPWR', probe.LARGE])
        self.assertEqual(calls['Xfine_regenerate1'],
                         ['Xfine_regenerate1', 'fine_node', 'OUT', 'VGND', 'VPWR', probe.LARGE])
        for input_value in (0, 1):
            values = dict(selected=1-input_value)
            for name in ('Xfine_regenerate0', 'Xfine_isolate', 'Xfine_regenerate1'):
                call = calls[name]
                values[call[2]] = 1-values[call[1]]
            self.assertEqual(values['OUT'], input_value)
            self.assertEqual(values['fine_node'], 1-input_value)
            self.assertEqual(values['conditioned'], input_value)
        for model in probe.source.native.definitions(bank):
            if model != probe.base.TOP:
                self.assertEqual(probe.source.cell_definition(bank, model),
                                 probe.source.cell_definition(result, model))
        new = {d['name']: d for d in observations['devices']}
        for device in old['devices']:
            if not device['name'].startswith(tuple(proof['changed_instance_prefixes'])):
                self.assertEqual(device, new[device['name']])
        self.assertFalse(proof['qualified_phy'])

    def test_changed_supply_ports_topology_unrelated_nodes_or_namespace_rejected(self):
        bank, observations, identity = self.material()
        cases = [bank.replace('Xfine_isolate selected fine_node', 'Xfine_isolate OUT fine_node', 1),
                 bank.replace('.subckt '+probe.SMALL+' A Y VGND VPWR',
                              '.subckt '+probe.SMALL+' Y A VGND VPWR', 1),
                 bank.replace('Xfine_regenerate0 fine_node restored_b VGND VPWR',
                              'Xfine_regenerate0 fine_node restored_b VPWR VGND', 1),
                 bank.replace('Xfine_isolate selected fine_node', 'Xfine_isolate conditioned fine_node', 1)]
        for candidate in cases:
            with self.assertRaises(ValueError):
                probe.transform(candidate, observations)
        changed = deepcopy(observations)
        changed['devices'][0]['terminals'][0] = 'unrelated_changed_signal'
        with self.assertRaisesRegex(ValueError, 'Unrelated native'):
            probe.transform(bank, changed)

    def test_original_stimulus_and_complete_unique_new_node_observations(self):
        bank, old, identity = self.material()
        result, observations, proof = probe.transform(bank, old)
        local = dict(identity, observations=observations)
        self.assertEqual([(s['coarse'], s['fine'], s['duty']) for s in probe.specifications()],
                         [(0, 0, .5), (0, 31, .6), (0, 31, .4), (1, 0, .5)])
        for spec in probe.specifications():
            text = probe.fixture(Path('/unused'), local, spec)
            self.assertIn('.tran 2p 25n 0 2p', text)
            self.assertIn('VDD VDD 0 1.8', text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12', text)
            self.assertEqual(text.count('tanh('), 16)
            translated, names = runner.translate(text)
            self.assertEqual(len(names), len(set(names)))
            self.assertIn('v(xd.conditioned)', names)
            self.assertIn('v(xd.fine_node)', names)
            self.assertNotIn('v(xd.restored_b)', names)
            self.assertGreater(len(names), 1500)
            self.assertIn(probe.TOP, text)

    def rows(self):
        rows = []
        for spec in probe.specifications():
            delay = {(0, 0): 500, (0, 31): 850, (1, 0): 700}[spec['coarse'], spec['fine']]
            rows.append(dict(spec=spec, error=None, result=dict(current_clock_interface_screen_passed=True,
                edge_delays_ps={e: [delay+k*.1 for k in range(8)] for e in ('rise', 'fall')})))
        return rows

    def test_all_original_gates_eight_pulses_and_both_overlap_edges_required(self):
        rows = self.rows()
        self.assertTrue(probe.compare(rows)['component_hypothesis_passed'])
        self.assertFalse(probe.compare(rows)['electrical_qualification_passed'])
        self.assertIsNone(probe.compare(rows[:3]))
        for cause in ('gate', 'missing', 'nonfinite', 'overlap'):
            changed = deepcopy(rows)
            if cause == 'gate': changed[0]['result']['current_clock_interface_screen_passed'] = False
            elif cause == 'missing': changed[1]['result']['edge_delays_ps']['rise'].pop()
            elif cause == 'nonfinite': changed[1]['result']['edge_delays_ps']['rise'][0] = float('nan')
            else: changed[3]['result']['edge_delays_ps']['fall'][-1] = 900
            self.assertFalse(probe.compare(changed)['component_hypothesis_passed'])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            probe.compare(list(reversed(rows)))

    def test_completed_zero_stage_receipt_binds_exact_original_case_and_delays(self):
        bank, observations, identity = self.material()
        original = probe.ROOT/identity['parent']
        baseline = identity['baseline_zero']
        evidence = probe.ROOT/'build/diagnostics/regular_regenerated_stages_v300/eeff61ca7936aa3c'
        result = probe.require_stage_reference(evidence, original, baseline)
        self.assertEqual(result['version'], probe.diagnosis.VERSION)
        changed = deepcopy(baseline)
        changed['task']['id'] = '1'
        with self.assertRaisesRegex(ValueError, 'baseline zero'):
            probe.require_stage_reference(evidence, original, changed)
        changed = deepcopy(baseline)
        changed['result']['edge_delays_ps']['fall'][0] += 1
        with self.assertRaisesRegex(ValueError, 'delays'):
            probe.require_stage_reference(evidence, original, changed)

    def test_actual_prepared_bank_and_all_four_decks_reproduce(self):
        parent = probe.ROOT/'build/diagnostics/preconditioned_fine_bank_v315/03aec7bd64badc04'
        if not (parent/'manifest.json').exists():
            self.skipTest('requires actual prepared preconditioned bank')
        manifest = json.loads((parent/'manifest.json').read_text())
        identity = manifest['identity']
        self.assertEqual(parent.name, hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16])
        self.assertEqual(probe.sha(parent/'bank.spice'), manifest['bank_sha256'])
        self.assertEqual((identity['max_workers'], identity['priority']), (1, 1))
        self.assertEqual(identity['native_revision']['node_polarities'],
                         dict(selected='inverting', conditioned='noninverting', fine_node='inverting'))
        pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in identity['ports']}
        devices = probe.source.native.mapped_mos((parent/'bank.spice').read_text(), probe.TOP, pins, 'XD')
        self.assertEqual(devices, identity['observations']['devices'])
        for k, task in enumerate(manifest['tasks']):
            self.assertEqual(task['spec'], probe.specifications()[k])
            self.assertEqual(probe.sha(parent/task['id']/'bench.cir'), task['deck_sha256'])
            self.assertEqual((parent/task['id']/'bench.cir').read_text(), probe.fixture(parent, identity, task['spec']))


if __name__ == '__main__':
    unittest.main()
