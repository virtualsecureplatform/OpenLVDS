# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_strong_counter_clear_v266 as diagnosis


class StrongCounterClearTests(unittest.TestCase):
    def fixture(self,prepare_fall):
        t=np.arange(0,26001.)
        def pulse(a,b):return .9*(np.tanh((t-a)/20)-np.tanh((t-b)/20))
        return t,dict(REQUEST=pulse(3400,21000)+.9*(1+np.tanh((t-23000)/20)),
                      PREPARE=pulse(8000,prepare_fall),RESET_N=pulse(10400,22804))

    def test_late_clear_fails_even_when_final_voltage_is_low(self):
        t,s=self.fixture(23038);r=diagnosis.clear_metrics(t,s)
        self.assertFalse(r['original_async_clear_gate_reproduced'])
        prep=r['outputs']['PREPARE']
        self.assertAlmostEqual(prep['external_reassert_headroom_ps'],-38)
        self.assertLess(prep['maximum_absolute_voltage_after_24ns_v'],.18)
        self.assertTrue(r['outputs']['RESET_N']['clear_before_external_reassert_passed'])

    def test_original_strict_clear_window_and_missing_edge_remain_required(self):
        t,s=self.fixture(22900)
        self.assertTrue(diagnosis.clear_metrics(t,s)['original_async_clear_gate_reproduced'])
        t,s=self.fixture(23000)
        self.assertFalse(diagnosis.clear_metrics(t,s)['original_async_clear_gate_reproduced'])
        s['PREPARE']=np.zeros_like(t)
        self.assertFalse(diagnosis.clear_metrics(t,s)['original_async_clear_gate_reproduced'])
        s['REQUEST']=np.zeros_like(t)
        with self.assertRaisesRegex(ValueError,'complete REQUEST'):diagnosis.clear_metrics(t,s)


if __name__=='__main__':unittest.main()
