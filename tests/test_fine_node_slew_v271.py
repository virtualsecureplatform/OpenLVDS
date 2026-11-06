# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_fine_node_slew_v271 as analysis


class FineNodeSlewTests(unittest.TestCase):
    def fixture(self,width):
        t=np.arange(0,26000,.5)
        v=sum(.9*(np.tanh((t-500-3000*k)/width)-np.tanh((t-2000-3000*k)/width)) for k in range(8))
        return t,v

    def test_full_eight_edge_histories_and_slew_domain(self):
        t,v=self.fixture(20);r=analysis.measure(t,v)
        self.assertTrue(r['within_current_250ps_output_domain'])
        for edge in ('rise','fall'):
            self.assertEqual(len(r['edges'][edge]['slews_10_90_ps']),8)
            self.assertAlmostEqual(r['edges'][edge]['maximum_ps'],40*np.arctanh(.8),delta=.01)
        t,v=self.fixture(120)
        self.assertFalse(analysis.measure(t,v)['within_current_250ps_output_domain'])

    def test_incomplete_internal_pulse_history_is_rejected(self):
        t,v=self.fixture(20);v[t>21000]=0
        with self.assertRaisesRegex(ValueError,'eight complete'):analysis.measure(t,v)


if __name__=='__main__':unittest.main()
