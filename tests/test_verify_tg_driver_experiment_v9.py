# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_tg_driver_experiment_v9 as proof


class DiagnosticAdmissionTests(unittest.TestCase):
    def rows(self):
        rows = []
        for spec in proof.pilot.specifications():
            delay = 400+100*spec['coarse']+5*spec['fine']
            result = dict(samples=[dict(rise_delay_ps=delay, fall_delay_ps=delay)]*2,
                          terminal_screen_passed=True, control_settling_passed=True,
                          onehot_control_settling_passed=True,
                          repeated_delay_difference_ps=dict(rise=0, fall=0),
                          zero_code_fast_quarter_headroom_ps=200 if spec['coarse'] == spec['fine'] == 0 else None)
            rows.append(dict(task=dict(spec=spec), result=result))
        return rows

    def test_complete_sparse_success_cannot_admit_borrowed_rc_or_phy(self):
        reports = proof.comparisons(self.rows())
        self.assertEqual({p['profile'] for p in reports}, set(proof.pilot.circuit.PROFILES))
        for p in reports:
            self.assertTrue(p['sparse_native_screen_passed'])
            for key in ('inverter_rc_physically_equivalent', 'whole_bank_rc_retained',
                        'electrical_qualification_passed', 'dense_legal_code_coverage_proven', 'qualified_phy'):
                self.assertFalse(p[key])

    def test_fine_gap_voltage_control_and_incomplete_points_still_reject(self):
        for fault in ('gap', 'voltage', 'control', 'incomplete'):
            rows = self.rows()
            profile = next(iter(proof.pilot.circuit.PROFILES))
            row = next(r for r in rows if r['task']['spec']['profile'] == profile and r['task']['spec']['fine'] == 16)
            if fault == 'gap':
                row['result']['samples'] = [dict(rise_delay_ps=501, fall_delay_ps=480)]*2
            elif fault == 'voltage':
                row['result']['terminal_screen_passed'] = False
            elif fault == 'control':
                row['result']['control_settling_passed'] = False
            else:
                rows.remove(row)
            reports = proof.comparisons(rows)
            self.assertFalse(next(p for p in reports if p['profile'] == profile)['sparse_native_screen_passed'], fault)
            self.assertTrue(all(p['sparse_native_screen_passed'] for p in reports if p['profile'] != profile))


if __name__ == '__main__':
    unittest.main()
