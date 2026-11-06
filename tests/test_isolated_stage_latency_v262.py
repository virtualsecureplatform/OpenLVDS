# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_isolated_stage_latency_v262 as diagnostic


class StageLatencyTests(unittest.TestCase):
    def fixture(self):
        t=np.arange(0,21000,.5)
        def train(delay):
            return sum(.9*(np.tanh((t-1000-2400*k-delay)/20)-np.tanh((t-2200-2400*k-delay)/20)) for k in range(8))
        return t,dict(input=train(0),selected=1.8-train(100),fine_node=train(250),output=train(600))

    def test_opposite_selected_polarity_and_all_eight_stage_sums(self):
        t,signals=self.fixture()
        result=diagnostic.decompose(t,signals,dict(rise=[600]*8,fall=[600]*8))
        for edge in ('rise','fall'):
            for stage,expected in zip(diagnostic.STAGES,(100,150,350)):
                np.testing.assert_allclose(result[edge]['stage_delays_ps'][stage],[expected]*8,atol=1e-8)
            self.assertLess(result[edge]['maximum_sum_residual_ps'],1e-8)

    def test_missing_internal_edge_or_changed_recorded_delay_is_rejected(self):
        t,signals=self.fixture();reference=dict(rise=[600]*8,fall=[600]*8)
        with self.assertRaisesRegex(ValueError,'reproduce'):
            diagnostic.decompose(t,signals,dict(rise=[601]*8,fall=[600]*8))
        signals['selected']=np.full_like(t,1.8)
        with self.assertRaisesRegex(ValueError,'eight matched'):
            diagnostic.decompose(t,signals,reference)


if __name__=='__main__':unittest.main()
