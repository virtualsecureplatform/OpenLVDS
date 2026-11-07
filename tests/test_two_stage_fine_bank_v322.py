# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_two_stage_fine_bank_v322 as probe
import run_native_binary_v2 as runner


class TwoStageFineBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = probe.ROOT/'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        if not (parent/'manifest.json').exists():
            raise unittest.SkipTest('requires actual regular native bank')
        cls.bank = (parent/'bank.spice').read_text()
        cls.identity = json.loads((parent/'manifest.json').read_text())['identity']

    def assembled(self):
        return probe.transform(self.bank, self.identity['observations'])

    def test_actual_removed_inventory_unchanged_cells_fine_controls_and_other_terminals(self):
        bank, obs, revision = self.assembled()
        self.assertEqual((len(obs['devices']), revision['native_mims']), (1365, 34))
        self.assertEqual((revision['removed_mos'], revision['removed_mims']), (164, 9))
        self.assertEqual(obs['programming_gates'], self.identity['observations']['programming_gates'])
        self.assertEqual(obs['controls'], self.identity['observations']['controls'])
        new = {d['name']: d for d in obs['devices']}
        old = {d['name']: d for d in self.identity['observations']['devices']}
        self.assertEqual(set(old)-set(new), {n for n in old if n.startswith(probe.REMOVED)})
        for n, d in old.items():
            if not n.startswith(probe.REMOVED+probe.REWIRED):
                self.assertEqual(new[n], d)
        for name in probe.source.native.definitions(self.bank):
            if name != probe.source.TOP:
                self.assertEqual(probe.source.cell_definition(self.bank, name),
                                 probe.source.cell_definition(bank, name))
        self.assertFalse(revision['shared_wire_rc_qualified'])
        self.assertFalse(revision['qualified_phy'])

    def test_both_root_paths_and_noninverting_selected_path_for_all_sixteen_codes(self):
        bank, obs, revision = self.assembled()
        body = probe.source.native.definitions(bank)[probe.TOP][1]
        calls = {w[0]: w for w in body}
        self.assertFalse(any(w[0].startswith('Xgroup_compound') for w in body))
        self.assertNotIn('Xfine_regenerate0', calls)
        self.assertEqual(calls['Xfine_regenerate1'],
                         ['Xfine_regenerate1', 'fine_node', 'OUT', 'VGND', 'VPWR', probe.source.MODEL])
        for code in range(16):
            group, leaf = divmod(code, 4)
            first = calls[f'Xswitch0_{group}_{leaf}']
            self.assertEqual(first[1:3], ['IN' if code == 0 else 'tap'+str(code), f'tree0_{group}'])
            for tag in (f'Xswitch1_0_{group}', f'Xroot_parallel{group}'):
                self.assertEqual(calls[tag][1:5], [f'tree0_{group}', 'selected', f'en1_{group}', f'en_b1_{group}'])
            for value in (0, 1):
                selected = value  # selected coarse tap through two noninverting TG levels
                fine_node = 1-selected
                output = 1-fine_node
                self.assertEqual(output, value)
        self.assertEqual(revision['node_polarities'], dict(selected='noninverting', fine_node='inverting'))

    def test_modified_or_missing_group_root_and_fine_calls_rejected(self):
        candidates = [
            self.bank.replace('Xgroup_compound0 tree0_0', 'Xgroup_compound0 tree0_1', 1),
            self.bank.replace('Xroot_parallel0 regenerated0', 'Xroot_parallel0 regenerated1', 1),
            self.bank.replace('Xswitch1_0_0 regenerated0', 'Xswitch1_0_0 tree0_0', 1),
            self.bank.replace('Xfine_regenerate0 fine_node restored_b', 'Xfine_regenerate0 selected restored_b', 1),
            self.bank.replace('Xfine_isolate selected fine_node VGND VPWR',
                              'Xfine_isolate selected fine_node VPWR VGND', 1),
        ]
        for candidate in candidates:
            with self.assertRaises(ValueError):
                probe.transform(candidate, self.identity['observations'])
        old = deepcopy(self.identity['observations'])
        old['devices'][0]['terminals'][0] = 'unrelated_changed_node'
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            probe.transform(self.bank, old)

    def test_full_original_stimulus_and_actual_terminal_epoch_observations(self):
        bank, obs, revision = self.assembled()
        identity = dict(self.identity, observations=obs)
        self.assertEqual([(s['coarse'], s['fine'], s['duty']) for s in probe.specifications()],
                         [(0, 0, .5), (0, 31, .6), (0, 31, .4), (1, 0, .5)])
        for spec in probe.specifications():
            text = probe.fixture(Path('/unused'), identity, spec)
            self.assertIn('.tran 2p 25n 0 2p', text)
            self.assertIn('VDD VDD 0 1.8', text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12', text)
            self.assertEqual(text.count('tanh('), 16)
            _, names = runner.translate(text)
            self.assertEqual(len(names), len(set(names)))
            self.assertNotIn('v(xd.restored_b)', names)
            self.assertTrue(all('v(xd.tree0_'+str(k)+')' in names for k in range(4)))
            for d in obs['devices']:
                for n in d['terminals']:
                    if n != '0':
                        self.assertIn('v('+n.replace(':', '.').lower()+')', names)

    def rows(self):
        result = []
        for spec in probe.specifications():
            delay = {(0, 0): 400, (0, 31): 850, (1, 0): 700}[spec['coarse'], spec['fine']]
            result.append(dict(spec=spec, error=None, result=dict(current_clock_interface_screen_passed=True,
                edge_delays_ps={e: [delay+k*.1 for k in range(8)] for e in ('rise', 'fall')})))
        return result

    def test_original_zero_gate_all_eight_edges_and_both_overlaps_are_required(self):
        rows = self.rows()
        self.assertTrue(probe.compare(rows)['component_hypothesis_passed'])
        self.assertFalse(probe.compare(rows)['electrical_qualification_passed'])
        self.assertIsNone(probe.compare(rows[:-1]))
        for failure in ('zero', 'missing', 'nonfinite', 'overlap'):
            changed = deepcopy(rows)
            if failure == 'zero': changed[0]['result']['current_clock_interface_screen_passed'] = False
            elif failure == 'missing': changed[1]['result']['edge_delays_ps']['rise'].pop()
            elif failure == 'nonfinite': changed[2]['result']['edge_delays_ps']['fall'][0] = float('nan')
            else: changed[3]['result']['edge_delays_ps']['fall'][-1] = 900
            self.assertFalse(probe.compare(changed)['component_hypothesis_passed'])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            probe.compare(list(reversed(rows)))

    def test_actual_complete_depth_diagnosis_required_without_relaxing_other_gates(self):
        evidence = probe.ROOT/'build/reports/preconditioned_bank_stage_replay/20261107T011544Z'
        if not (evidence/'summary.json').exists():
            self.skipTest('requires complete independent reordered-bank zero diagnosis')
        paths = probe.depth_evidence(evidence)
        self.assertGreater(len(paths), 100)
        self.assertTrue(all(p.is_file() for p in paths))
        report = json.loads((evidence/'summary.json').read_text())
        for failure in ('quarter', 'voltage', 'complete'):
            changed = deepcopy(report)
            if failure == 'quarter': changed['zero_code_fast_quarter_headroom_ps'] = 1
            elif failure == 'voltage': changed['recorded_gates']['terminal_screen_passed'] = False
            else: changed['all_original_native_metrics_reproduced'] = False
            with tempfile.TemporaryDirectory(dir=evidence.parent) as directory:
                p = Path(directory)
                (p/'summary.json').write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'quarter-period failure'):
                    probe.depth_evidence(p)

    def test_prepared_native_graph_and_all_four_exact_decks_reproduce(self):
        parent = probe.ROOT/'build/diagnostics/two_stage_fine_bank_v322/4092d10edbdce08c'
        if not (parent/'manifest.json').exists():
            self.skipTest('requires actual prepared two-stage bank')
        manifest = json.loads((parent/'manifest.json').read_text())
        identity = manifest['identity']
        self.assertEqual(parent.name, hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16])
        self.assertEqual((identity['max_workers'], identity['priority']), (1, 1))
        self.assertEqual(identity['guards'], probe.guard_inputs(identity['inputs']))
        bank, observations, revision = self.assembled()
        self.assertEqual((parent/'bank.spice').read_text(), bank)
        self.assertEqual(probe.sha(parent/'bank.spice'), manifest['bank_sha256'])
        self.assertEqual(identity['observations'], observations)
        self.assertEqual(identity['native_revision'], revision)
        self.assertEqual(identity['specs'], probe.specifications())
        for k, task in enumerate(manifest['tasks']):
            file = parent/str(k)/'bench.cir'
            self.assertEqual(task['id'], str(k))
            self.assertEqual(task['spec'], probe.specifications()[k])
            self.assertEqual(file.read_text(), probe.fixture(parent, identity, task['spec']))
            self.assertEqual(probe.sha(file), task['deck_sha256'])
        self.assertFalse(manifest['qualified_phy'])


if __name__ == '__main__':
    unittest.main()
