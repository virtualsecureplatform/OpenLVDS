# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import matrix_receiver_differential_restore as matrix


class DifferentialMatrixGates(unittest.TestCase):
    def rows(self, count=15):
        return [dict(results=[dict(task=v, passed=True,
            metrics=dict(metrics=dict(passed=True)),
            terminal_observations=dict(observed_thin_guard_passed=True))
            for v in matrix.pilot.VARIANTS]) for _ in range(count)]

    def test_incomplete_or_electrically_failed_candidate_cannot_receive_admission(self):
        for count in [0, 6, 14]:
            self.assertFalse(any(g['source_dc_passed'] for g in matrix.admission(self.rows(count)).values()))
        rows=self.rows()
        for field in ['passed', 'sensitivity', 'stress']:
            failed=deepcopy(rows); row=failed[-1]['results'][1]
            if field=='passed': row['passed']=False
            elif field=='sensitivity': row['metrics']['metrics']['passed']=False
            else: row['terminal_observations']['observed_thin_guard_passed']=False
            gates=matrix.admission(failed)
            self.assertFalse(gates['track_t8_r7']['source_dc_passed'])
            self.assertEqual(gates['track_t8_r7']['passed_cases'],14)
            self.assertTrue(gates['control']['source_dc_passed'])
            self.assertTrue(gates['track_t16_r7']['source_dc_passed'])

    def test_named_variants_are_measured_independently_of_result_order(self):
        rows=self.rows()
        for case in rows: case['results'].reverse()
        self.assertTrue(all(g['source_dc_passed'] for g in matrix.admission(rows).values()))
        rows[0]['results'].pop()
        with self.assertRaises(StopIteration): matrix.admission(rows)

    def test_coverage_rejects_duplicate_missing_and_mislabelled_pvt(self):
        req=dict(process_corners=['tt','ff','ss','fs','sf'], temperatures_c=[0,25,40])
        children=[dict(process=p,temperature=t,case=f'schematic_receiver_{p}_{t}')
                  for p in req['process_corners'] for t in req['temperatures_c']]
        matrix.coverage(children,req)
        duplicate=deepcopy(children);duplicate[-1]=deepcopy(duplicate[0])
        mislabelled=deepcopy(children);mislabelled[-1]['case']='schematic_receiver_tt_25'
        for bad in [children[:-1],duplicate,mislabelled]:
            with self.assertRaises(ValueError):matrix.coverage(bad,req)
        self.assertIn(('ss',40),matrix.PILOTS)
        self.assertIn(('ff',40),matrix.PILOTS)
