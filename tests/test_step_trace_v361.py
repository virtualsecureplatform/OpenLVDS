# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_step_trace_v361 as p


class StepTraceTests(unittest.TestCase):
    def trace(self,node='vdd#branch',flag=0):
        return 'OLVDS_STEP kind=ni_limit t=0 iter=101 noncon=593 device=- node=-\n'+''.join(
            f'OLVDS_STEP kind=ni_limit t={k*1e-13} iter=101 noncon={flag} device=- node={node}\n'
            f'OLVDS_STEP kind=noncon_reject t={k*1e-13} dt=1e-13 status=103\n' for k in range(1,61))

    def test_identify_supply_current_only_with_zero_model_flags_and_paired_rejections(self):
        r=p.analyze(self.trace());self.assertTrue(r['supply_current_iteration_bottleneck_observed'])
        self.assertEqual(r['positive_time_counts']['ni_limit'],60)
        self.assertEqual(r['all_logged_counts']['ni_limit'],61)
        self.assertEqual(r['model_nonconvergence_flags'],{0:60});self.assertFalse(r['qualified_phy'])

    def test_model_or_other_node_or_charge_error_cannot_match_supply_current_diagnosis(self):
        self.assertFalse(p.analyze(self.trace(flag=1))['supply_current_iteration_bottleneck_observed'])
        self.assertFalse(p.analyze(self.trace(node='xd.selected'))['supply_current_iteration_bottleneck_observed'])
        self.assertFalse(p.analyze(self.trace()+'OLVDS_STEP kind=charge_trunc t=1e-12\n')['supply_current_iteration_bottleneck_observed'])
        self.assertFalse(p.analyze(self.trace()+'OLVDS_STEP kind=trunc_decision t=1e-12 reject=1\n')['supply_current_iteration_bottleneck_observed'])

    def test_ignore_nontrace_text_and_reject_nonfinite_observations(self):
        self.assertEqual(p.analyze('startup notes\n')['positive_time_counts'],{})
        with self.assertRaises(ValueError):p.analyze('OLVDS_STEP kind=ni_success t=nan\n')
        with self.assertRaises(ValueError):p.analyze('OLVDS_STEP kind=ni_success t=1e-9\n')


if __name__=='__main__':unittest.main()
