# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_mim_isolated_fine_bank_v321 as probe
import run_native_binary_v2 as runner


class MimIsolatedFineBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = probe.ROOT/'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        proof = probe.ROOT/'build/diagnostics/retained_mim_fine_rc_v320/ddf3c29ce3fc44da'
        if not (parent/'manifest.json').exists() or not (proof/'summary.json').exists():
            raise unittest.SkipTest('requires actual native bank and qualified MIM components')
        cls.parent = parent
        cls.components = proof
        cls.identity = json.loads((parent/'manifest.json').read_text())['identity']
        cls.bank = (parent/'bank.spice').read_text()
        cls.cells = {r['variant']: probe.source.cell_definition(
            (probe.ROOT/r['extraction']['netlist']).read_text(), r['macro'])
            for r in json.loads((proof/'summary.json').read_text())['rows']}

    def assembled(self, variant):
        return probe.transform(self.bank, self.identity['observations'], self.cells[variant], variant)

    def test_both_actual_native_graphs_preserve_nonfine_and_observe_every_switch(self):
        old = self.identity['observations']
        for variant in probe.MODELS:
            bank, obs, revision = self.assembled(variant)
            self.assertEqual((len(obs['devices']), revision['native_mims']), (1467, 74))
            self.assertEqual(obs['controls'], old['controls'])
            self.assertEqual(len(obs['programming_gates']), 173)
            devices = {d['name']: d for d in obs['devices']}
            for d in old['devices']:
                if not d['name'].startswith(probe.PREFIXES):
                    self.assertEqual(devices[d['name']], d)
            gates = {g['device']: g for g in obs['programming_gates']}
            for k, prefix in enumerate(probe.PREFIXES):
                self.assertEqual({n for n in devices if n.startswith(prefix)},
                                 {prefix+x for x in ('X0', 'X3', 'X4')})
                for leaf, control in (('X0', f'fine_b{k}'), ('X3', f'fine{k}'), ('X4', f'fine_b{k}')):
                    self.assertEqual(gates[prefix+leaf]['control'], control)
                    self.assertEqual(gates[prefix+leaf]['gate_node'], devices[prefix+leaf]['terminals'][1])
            for name in probe.source.native.definitions(self.bank):
                if name != probe.source.TOP:
                    self.assertEqual(probe.source.cell_definition(self.bank, name),
                                     probe.source.cell_definition(bank, name))
            self.assertEqual(probe.source.native.definitions(bank)[probe.MODELS[variant]][0], probe.PORTS)
            self.assertFalse(revision['qualified_phy'])

    def test_changed_supplies_wiring_namespace_and_missing_gate_coverage_rejected(self):
        old = self.identity['observations']
        for candidate in (self.bank.replace('Xfine_unit0 fine_node fine0 fine_b0 VPWR VGND',
                                          'Xfine_unit0 fine_node fine0 fine_b0 VGND VPWR', 1),
                          self.bank.replace('Xfine_unit0 fine_node', 'Xfine_unit0 selected', 1)):
            with self.assertRaisesRegex(ValueError, 'wiring'):
                probe.transform(candidate, old, self.cells['2x2'], '2x2')
        cell = self.cells['2x2'].replace(' NODE EN ENB VDD VSS', ' NODE EN ENB VSS VDD', 1)
        with self.assertRaisesRegex(ValueError, 'port order'):
            probe.transform(self.bank, old, cell, '2x2')
        with self.assertRaisesRegex(ValueError, 'namespace'):
            probe.transform(self.bank, old, self.cells['2x3'].replace('l=3', 'l=4', 1), '2x3')
        changed = deepcopy(old)
        changed['devices'][0]['terminals'][0] = 'changed_unrelated_node'
        with self.assertRaisesRegex(ValueError, 'Non-fine'):
            probe.transform(self.bank, changed, self.cells['2x2'], '2x2')
        changed = deepcopy(old)
        changed['programming_gates'] = [g for g in changed['programming_gates']
                                      if g['device'] != 'XD:Xfine_unit0:X5']
        with self.assertRaisesRegex(ValueError, 'coverage'):
            probe.transform(self.bank, changed, self.cells['2x2'], '2x2')

    def test_unchanged_eight_cycle_native_stimulus_and_all_terminal_observations(self):
        libraries = {v: self.assembled(v) for v in probe.MODELS}
        identity = dict(self.identity, observations={v: libraries[v][1] for v in probe.MODELS})
        self.assertEqual(len(probe.specifications()), 8)
        for spec in probe.specifications():
            variant = spec['fine_cell']
            text = probe.fixture(Path('/unused'), identity, spec)
            self.assertIn('.tran 2p 25n 0 2p', text)
            self.assertIn('VDD VDD 0 1.8', text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12', text)
            self.assertEqual(text.count('tanh('), 16)
            original = probe.source.fixture(Path('/unused')/variant,
                dict(identity, observations=identity['observations'][variant]), spec)
            self.assertEqual(text, original.replace(probe.source.TOP, probe.TOP, 1)
                .replace('OpenLVDS '+probe.source.VERSION+'\n', 'OpenLVDS '+probe.VERSION+'\n', 1))
            _, names = runner.translate(text)
            self.assertEqual(len(names), len(set(names)))
            for d in identity['observations'][variant]['devices']:
                for node in d['terminals']:
                    if node != '0':
                        self.assertIn('v('+node.replace(':', '.').lower()+')', names)

    def rows(self):
        rows = []
        for spec in probe.specifications():
            delay = {(0, 0): 500, (0, 31): 850, (1, 0): 700}[spec['coarse'], spec['fine']]
            rows.append(dict(spec=spec, error=None, result=dict(current_clock_interface_screen_passed=True,
                edge_delays_ps={e: [delay+k*.1 for k in range(8)] for e in ('rise', 'fall')})))
        return rows

    def test_both_fine_endpoints_eight_edges_and_zero_gate_required_per_variant(self):
        rows = self.rows()
        self.assertTrue(probe.compare(rows)['any_component_hypothesis_passed'])
        self.assertFalse(probe.compare(rows)['electrical_qualification_passed'])
        self.assertIsNone(probe.compare(rows[:-1]))
        for failure in ('zero', 'missing', 'nonfinite', 'overlap'):
            changed = deepcopy(rows)
            for index in (0, 4):
                if failure == 'zero': changed[index]['result']['current_clock_interface_screen_passed'] = False
                elif failure == 'missing': changed[index+1]['result']['edge_delays_ps']['rise'].pop()
                elif failure == 'nonfinite': changed[index+2]['result']['edge_delays_ps']['rise'][0] = float('nan')
                else: changed[index+3]['result']['edge_delays_ps']['fall'][-1] = 900
            self.assertFalse(probe.compare(changed)['any_component_hypothesis_passed'])
        with self.assertRaisesRegex(ValueError, 'all original'):
            probe.compare(list(reversed(rows)))

    def test_only_historical_raw_is_deferred_from_per_lease_guard(self):
        inputs = {n: n for n in ('build/diagnostics/source/0/bench.raw', 'build/extracted/model.raw',
            'scripts/native_binary_raw_v2.py', 'build/diagnostics/source/0/bench.cir',
            'build/diagnostics/retained/proof.json', 'build/extracted/model.spice')}
        self.assertEqual(set(inputs)-set(probe.guard_inputs(inputs)), {'build/diagnostics/source/0/bench.raw'})

    def test_actual_current_mim_proof_and_unchanged_models_are_required(self):
        cells, files, identity = probe.materials(self.components)
        self.assertEqual(cells, self.cells)
        self.assertGreater(len(files), 70)
        self.assertTrue(all(p.is_file() for p in files))
        self.assertEqual(identity['version'],
            'retained-mim-fine-cells-unchanged-rc-native-schur-requalification-v320.1')


if __name__ == '__main__':
    unittest.main()
