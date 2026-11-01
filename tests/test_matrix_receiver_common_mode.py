# SPDX-License-Identifier: GPL-3.0-only
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import matrix_receiver_common_mode as matrix


class CommonModeMatrix(unittest.TestCase):
    def setUp(self):
        self.requirements = dict(process_corners=['tt', 'ff', 'ss', 'fs', 'sf'], temperatures_c=[0, 25, 40])
        self.children = [dict(process=p, temperature=t, case=f'schematic_receiver_{p}_{t}')
                         for p in self.requirements['process_corners'] for t in self.requirements['temperatures_c']]
        self.results = [dict(results=[dict(task=v, passed=True, metrics=dict(metrics=dict(passed=True)),
            twelve_device_observations=dict(observed_thin_guard_passed=True)) for v in matrix.pilot.VARIANTS])
            for _ in range(15)]

    def test_requires_exact_process_temperature_coverage_and_labels(self):
        matrix.coverage(self.children, self.requirements)
        for bad in [self.children[:-1], self.children[:-1]+[self.children[0]],
                    self.children[:-1]+[dict(process='sf', temperature=41, case='schematic_receiver_sf_41')],
                    self.children[:-1]+[dict(self.children[-1], case='schematic_receiver_tt_25')]]:
            with self.assertRaises(ValueError):
                matrix.coverage(bad, self.requirements)

    def test_admission_does_not_borrow_other_variant_or_partial_coverage(self):
        self.assertTrue(all(g['source_dc_passed'] for g in matrix.admission(self.results).values()))
        self.assertFalse(any(g['source_dc_passed'] for g in matrix.admission(self.results[:3]).values()))
        self.assertTrue(all(g['source_dc_passed'] for g in matrix.admission(self.results[:3], required=3).values()))
        self.results[-1]['results'][1]['metrics']['metrics']['passed'] = False
        gates = matrix.admission(self.results)
        self.assertFalse(gates['reference_return']['source_dc_passed'])
        self.assertEqual(gates['reference_return']['passed_cases'], 14)
        self.assertTrue(gates['rail_pullup']['source_dc_passed'])

    def test_each_pass_flag_and_observed_stress_are_required(self):
        row = self.results[0]['results'][0]
        for key in ['passed', 'metrics', 'stress']:
            bad = copy.deepcopy(row)
            if key == 'passed':
                bad['passed'] = False
            elif key == 'metrics':
                bad['metrics']['metrics']['passed'] = False
            else:
                bad['twelve_device_observations']['observed_thin_guard_passed'] = False
            self.assertFalse(matrix.passed(bad))


if __name__ == '__main__':
    unittest.main()
