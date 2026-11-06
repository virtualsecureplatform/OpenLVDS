# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_fast_clear_counter_v299 as diagnosis


class FastCounterClearTests(unittest.TestCase):
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

    def test_completed_low_and_high_native_receipt_retains_all_metrics_and_positive_clear_margin(self):
        folder=diagnosis.ROOT/'build/diagnostics/fast_clear_counter_clear_diagnosis_v299/9be3b323704290c8'
        if not folder.exists():self.skipTest('Completed fast-clear native receipt required')
        m=json.loads((folder/'manifest.json').read_text());r=json.loads((folder/'summary.json').read_text())
        self.assertEqual(len(r['rows']),2);self.assertFalse(r['qualified_phy'])
        for row in r['rows']:
            self.assertEqual(row['native_mos_observed'],644);self.assertTrue(row['original_metrics_reproduced'])
            self.assertTrue(row['terminal_screen_passed']);self.assertLessEqual(row['maximum_terminal_difference_v'],1.95)
            self.assertTrue(row['clear']['original_async_clear_gate_reproduced'])
            for v in row['clear']['outputs'].values():self.assertGreater(v['external_reassert_headroom_ps'],0)
            name=row['case']+'/summary.json'
            self.assertEqual(diagnosis.sha(diagnosis.ROOT/name),m['identity']['inputs'][name])
        high=r['rows'][1]['clear']['outputs']['PREPARE']
        self.assertAlmostEqual(high['external_reassert_headroom_ps'],159.82737307290517,places=6)
        old=diagnosis.ROOT/'build/diagnostics/strong_counter_clear_diagnosis_v266/06bdfd120dd71fed/summary.json'
        if old.exists():
            rows=json.loads(old.read_text())['rows']
            prior=next(row for row in rows if row['task']['spec']['stop_level']==1)
            self.assertLess(prior['clear']['outputs']['PREPARE']['external_reassert_headroom_ps'],0)


if __name__=='__main__':unittest.main()
