# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_weighted_routed_v2 as verification


def rows():
    result=[]
    for spec in verification.pilot.specifications():
        base=500+100*spec['coarse']
        samples=[dict(code=code,rise_delay_ps=base+5*code,fall_delay_ps=base+5*code+10,pulse_integrity_passed=True)
                 for code in verification.pilot.CODES]
        result.append(dict(task={'spec':spec},result=dict(samples=samples,pulse_integrity_passed=True,
            routed_control_settling_passed=True,terminal_screen_passed=True,minimum_quarter_headroom_ps=99 if spec['coarse']==0 else None)))
    return result


class RoutedSparseScreenTests(unittest.TestCase):
    def test_good_sparse_screen_still_cannot_admit_a_code_table_or_phy(self):
        r=verification.assess(rows());self.assertTrue(r['sampled_sparse_screen_passed'])
        self.assertFalse(r['legal_code_table_admitted']);self.assertFalse(r['qualified_phy'])
        self.assertEqual(len(r['observed_single_code_steps']),8)

    def test_control_stress_carry_gap_and_repeat_failures_cannot_be_hidden_by_valid_pulses(self):
        for failure in ['routed_control_settling_passed','terminal_screen_passed','carry','gap','repeat']:
            data=deepcopy(rows())
            if failure in ['routed_control_settling_passed','terminal_screen_passed']:data[0]['result'][failure]=False
            elif failure=='carry':data[0]['result']['samples'][3]['fall_delay_ps']-=20
            elif failure=='gap':
                for s in data[1]['result']['samples']:
                    s['rise_delay_ps']+=200;s['fall_delay_ps']+=200
            else:data[0]['result']['samples'][-1]['rise_delay_ps']+=30
            with self.subTest(failure=failure):self.assertFalse(verification.assess(data)['sampled_sparse_screen_passed'])

    def test_missing_pulses_or_incomplete_cases_cannot_be_treated_as_delay_samples(self):
        data=rows();data[0]['result']['pulse_integrity_passed']=False
        data[0]['result']['samples'][0]['rise_delay_ps']=None
        self.assertFalse(verification.assess(data)['sampled_sparse_screen_passed'])
        with self.assertRaises(ValueError):verification.assess(data[:1])


if __name__=='__main__':unittest.main()
