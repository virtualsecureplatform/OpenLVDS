# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_iterations_v2 as pilot


class DcdlIterationTests(unittest.TestCase):
    def test_only_iteration_limit_and_title_change(self):
        body='.options timeint method=gear reltol=1e-4 abstol=1e-12\nX0 IN OUT cell\n.tran 2p 20n 0 2p\n.print tran V(IN) V(OUT)\n.end\n'
        original='OpenLVDS '+pilot.parent_pilot.VERSION+'\n'+body
        changed=pilot.fixture(original)
        self.assertEqual(changed,'OpenLVDS '+pilot.VERSION+'\n.options itl4=100\n'+body)
        for original in ['wrong title\n'+body,'OpenLVDS '+pilot.parent_pilot.VERSION+'\n.options itl4=20\n'+body]:
            with self.assertRaises(ValueError):pilot.fixture(original)

class IterationComparisonTests(unittest.TestCase):
    def test_comparison_requires_identical_pulse_epochs_and_mos_coverage(self):
        import copy
        import verify_dcdl_iterations_v2 as verifier
        a=dict(samples=[dict(pulse=0,rise_delay_ps=100,fall_delay_ps=110),dict(pulse=1,rise_delay_ps=101,fall_delay_ps=111)],
               terminal_stress=[dict(device='X0',max_terminal_difference_v=1.9),dict(device='X1',max_terminal_difference_v=1.85)],native_pulse_passed=True)
        b=copy.deepcopy(a);b['samples'][1]['fall_delay_ps']+=.75;b['terminal_stress'][1]['max_terminal_difference_v']+=.003
        result=verifier.compare(a,b)
        self.assertEqual(result['maximum_absolute_edge_delay_difference_ps'],.75)
        self.assertAlmostEqual(result['maximum_absolute_mos_peak_difference_v'],.003)
        for key in ['samples','terminal_stress']:
            bad=copy.deepcopy(b);bad[key].pop()
            with self.assertRaises(ValueError):verifier.compare(a,bad)


if __name__=='__main__':unittest.main()
