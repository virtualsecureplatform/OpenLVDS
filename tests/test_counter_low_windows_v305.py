# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_counter_low_windows_v305 as p


class CounterLowWindowTests(unittest.TestCase):
    def fixture(self,offset=-20):
        t=np.arange(0,26000.5,.5);period=2440.;rises=[2000+k*period for k in range(7)]
        clk=sum(.9*(np.tanh((t-r)/40)-np.tanh((t-r-.6*period)/40)) for r in rises)
        up=p.crossings(t,clk,.18,True)
        def step(event):return 1.8*np.clip((t-event+10)/20,0,1)
        signals=dict(CLK=clk,**{stage:step(up[k+1]+offset) for k,stage in enumerate(p.STAGES)})
        return t,signals

    def test_three_fixed_epochs_match_actual_voltage_windows_and_positive_headroom(self):
        t,s=self.fixture();r=p.windows(t,s)
        self.assertTrue(r['all_three_assertions_in_original_low_windows'])
        self.assertAlmostEqual(r['minimum_remaining_low_window_ps'],20,places=6)
        self.assertGreater(r['minimum_clock_low_voltage_margin_v'],0)
        for k,row in enumerate(r['stages']):
            self.assertAlmostEqual(row['preceding_clock_rise_ps'],2000+2440*k,places=6)
            self.assertAlmostEqual(row['next_clock_rise_ps'],2000+2440*(k+1),places=6)
            self.assertGreater(row['guaranteed_low_window_ps'],800)

    def test_assertion_before_half_supply_rise_can_still_violate_original_point18_gate(self):
        t,s=self.fixture(20);r=p.windows(t,s)
        self.assertFalse(r['all_three_assertions_in_original_low_windows'])
        self.assertAlmostEqual(r['minimum_remaining_low_window_ps'],-20,places=6)
        for row in r['stages']:
            self.assertLess(row['assertion_ps'],row['next_clock_rise_ps'])
            self.assertGreater(row['clock_voltage_at_assertion_v'],.18)
            self.assertLess(row['clock_voltage_at_assertion_v'],.9)

    def test_late_assertion_does_not_wrap_to_another_clock_epoch(self):
        t,s=self.fixture();s['low0']=1.8*np.clip((t-4540+10)/20,0,1)
        r=p.windows(t,s);low0=r['stages'][0]
        self.assertAlmostEqual(low0['next_clock_rise_ps'],4440,places=6)
        self.assertLess(low0['remaining_low_window_ps'],-100)
        self.assertFalse(low0['assertion_in_original_low_window'])

    def test_missing_clock_phase_startup_or_nonfinite_data_is_rejected(self):
        t,s=self.fixture();s['low0']=np.zeros_like(t)
        with self.assertRaisesRegex(ValueError,'phase assertion'):p.windows(t,s)
        t,s=self.fixture();s['CLK']=np.zeros_like(t)
        with self.assertRaisesRegex(ValueError,'seven original'):p.windows(t,s)
        t,s=self.fixture();s['armed'][10]=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'):p.windows(t,s)
        t,s=self.fixture()
        with self.assertRaises(ValueError):p.windows(t[1:],{k:v[1:] for k,v in s.items()})
        with self.assertRaises(ValueError):p.windows(t[::-1],{k:v[::-1] for k,v in s.items()})

    def test_completed_native_receipt_separates_clear_success_from_fixed_epoch_low_failure(self):
        folder=p.ROOT/'build/diagnostics/counter_low_windows_v305/62b7bd0dcde80cc2'
        if not folder.exists():self.skipTest('Completed original native low-window receipt required')
        manifest=json.loads((folder/'manifest.json').read_text());result=json.loads((folder/'summary.json').read_text())
        self.assertEqual(len(result['rows']),4);self.assertFalse(result['qualified_phy'])
        for name,digest in manifest['identity']['inputs'].items():self.assertEqual(p.sha(p.ROOT/name),digest,name)
        original=next(r for r in result['rows'] if r['native_mos_observed']==612 and r['task']['spec']['duty']==.6)
        self.assertTrue(original['original_clear']['original_async_clear_gate_reproduced'])
        self.assertFalse(original['low_windows']['all_three_assertions_in_original_low_windows'])
        self.assertFalse(original['recorded_gates']['phase_arming_passed'])
        stages={r['stage']:r for r in original['low_windows']['stages']}
        self.assertAlmostEqual(stages['low0']['remaining_low_window_ps'],-90.18751240455458)
        self.assertAlmostEqual(stages['armed']['remaining_low_window_ps'],-10.258011605736101)
        self.assertLess(stages['low0']['assertion_ps'],stages['low0']['next_clock_rise_ps'])
        for row in result['rows']:
            if row['native_mos_observed']==644:
                self.assertTrue(row['low_windows']['all_three_assertions_in_original_low_windows'])
                self.assertAlmostEqual(row['low_windows']['minimum_remaining_low_window_ps'],17.560374989064258)


if __name__=='__main__':unittest.main()
