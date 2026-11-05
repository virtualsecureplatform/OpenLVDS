# SPDX-License-Identifier: GPL-3.0-only
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_dcdl_uniform_tree_v3 as verifier


class UniformTreeComparisonTests(unittest.TestCase):
    def rows(self):
        rows = []
        for n, spec in enumerate(verifier.pilot.specifications()):
            delay = 200+100*spec['coarse']+5*spec['fine']
            rows.append(dict(task=dict(id=str(n), spec=spec), result=dict(samples=[
                dict(rise_delay_ps=delay, fall_delay_ps=delay+10),
                dict(rise_delay_ps=delay, fall_delay_ps=delay+10)])))
        return rows

    def test_sparse_success_does_not_prove_dense_coverage(self):
        result = verifier.compare(self.rows())
        self.assertTrue(result['sampled_fine_order_passed'])
        self.assertTrue(result['coarse_overlap_passed'])
        self.assertEqual(result['coarse_overlap']['rise_ps'], 55)
        self.assertFalse(result['dense_legal_code_coverage_proven'])
        intervals = [s for s in result['fine_steps'] if s['to_fine']-s['from_fine'] > 1]
        self.assertTrue(all(s['adjacent_gap_passed'] is None for s in intervals))

    def test_carry_reversal_gap_and_coarse_hole_detected(self):
        rows = self.rows()
        bad = copy.deepcopy(rows)
        for row in bad:
            spec = row['task']['spec']
            for sample in row['result']['samples']:
                if spec['fine'] == 16:
                    sample['rise_delay_ps'] -= 10
                if spec['coarse'] == 1:
                    sample['fall_delay_ps'] += 1000
        result = verifier.compare(bad)
        self.assertFalse(result['sampled_fine_order_passed'])
        self.assertFalse(result['coarse_overlap_passed'])
        carry = [s for s in result['fine_steps'] if s['edge'] == 'rise' and s['from_fine'] == 15]
        self.assertTrue(all(not s['adjacent_gap_passed'] for s in carry))

    def test_missing_or_duplicate_codes_rejected(self):
        rows = self.rows()
        for bad in (rows[:-1], rows+[rows[0]], rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):
                verifier.compare(bad)


if __name__ == '__main__':
    unittest.main()
