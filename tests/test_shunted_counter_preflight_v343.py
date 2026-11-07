# SPDX-License-Identifier: GPL-3.0-only
"""Guard complete native timing evidence and physical shunt topology."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import preflight_shunted_counter_v343 as p


class ShuntedCounterPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((p.BOUNDARY/'manifest.json').read_text())
        cls.state = json.loads((p.BOUNDARY/'state.json').read_text())
        cls.report = json.loads((p.BOUNDARY/'summary.json').read_text())
        cls.plan = json.loads((p.PLAN/'manifest.json').read_text())['identity']

    def test_actual_twelve_passed_points_required_including_final_stress_and_window(self):
        p.require_boundaries(self.manifest, self.state, self.report)
        for key in ('terminal_screen_passed', 'stopped_clock_intermediate_clear_passed'):
            report = deepcopy(self.report)
            report['rows'][11]['result'][key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.require_boundaries(self.manifest, self.state, report)
        with self.assertRaises(ValueError):
            p.require_boundaries(self.manifest, dict(self.state, status='running'), self.report)
        with self.assertRaises(ValueError):
            p.require_boundaries(self.manifest, self.state, dict(self.report, rows=self.report['rows'][:11]))

    def test_exact_added_shunt_electrodes_and_unchanged_twenty_two_roles(self):
        old = self.plan['cells']
        cells = p.add_shunt(old)
        self.assertEqual(cells[:-1], old)
        self.assertEqual(cells[-1], dict(name=p.ROLE, model=p.CAP, pins=dict(Y='low0_sn', VGND='VGND')))
        self.assertEqual(len(cells), 23)
        wrong = deepcopy(old)
        next(c for c in wrong if c['name'] == 'low0_set_pair')['pins']['Y'] = 'wrong_output'
        with self.assertRaises(ValueError):
            p.add_shunt(wrong)
        with self.assertRaises(ValueError):
            p.add_shunt(cells)

    def test_actual_reference_matches_passed_native_parameters_and_complete_inventory(self):
        macros = deepcopy(self.plan['macros'])
        macros[p.CAP] = dict(folder='build/diagnostics/counter_output_mim5_physical_v336/80531cf7f88fa1a5')
        text = p.reference(p.add_shunt(self.plan['cells']), macros)
        ports, leaves = p.legacy.inventory.native_leaves(text, p.NAME)
        self.assertEqual(ports, p.PORTS)
        self.assertEqual(sum('fet_' in d['model'] for d in leaves), 744)
        self.assertEqual(sum('cap_mim' in d['model'] for d in leaves), 51)
        actual = (p.BOUNDARY/'cells.spice').read_text()+'\n'+(p.BOUNDARY/'pair.spice').read_text()
        _, expected = p.legacy.inventory.native_leaves(p.collapse(actual), p.legacy.base.NAME)
        result = p.legacy.inventory.compare_parameters(leaves, expected)
        self.assertTrue(result['native_parameters_preserved'])
        self.assertTrue(result['all_reference_supplied_junctions_preserved'])

    def test_conflicting_frozen_input_hashes_are_rejected(self):
        expected = {'native': 'original'}
        p.merge_expected(expected, {'native': 'original'})
        with self.assertRaisesRegex(ValueError, 'Conflicting captured'):
            p.merge_expected(expected, {'native': 'different'})


if __name__ == '__main__':
    unittest.main()
