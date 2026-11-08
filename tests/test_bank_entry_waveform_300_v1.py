# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_entry_waveform_300_v1 as p
import two_bank_native_measure_300_v1 as old
import two_bank_independent_measure_300_v1 as independent
from replay_bank_300_v2 import same


class EntryReferenceTests(unittest.TestCase):
    def spec(self,slew=250,duty=.6):
        return dict(frequency_mhz=310,input_slew_ps=slew,duty=duty,cycles=8,stop_ns=40,coarse=0,fine=0)

    def stage_result(self,s):
        t=np.arange(40001,dtype=np.float64)
        vin=p.evaluate(t,s);out=p.evaluate(t-700,dict(s,input_slew_ps=20))
        recorded=old.stage(t,vin,out,s,ideal_input=True)
        return t,vin,out,dict(banks=dict(first=dict(timing=recorded,terminal_screen_passed=True,
            control_settling_passed=True,external_controls=[],bank_screen_passed=False),
            next=dict(bank_screen_passed=True)),fixed_supply_passed=True)

    def test_all_eight_exact_entry_edges_and_independent_voltage_function(self):
        for slew in (20,250):
            for duty in (.4,.6):
                s=self.spec(slew,duty);points=p.points(s)
                self.assertEqual(len(points),82)
                self.assertTrue(all(a[0]<b[0] for a,b in zip(points,points[1:])))
                t=np.unique(np.r_[np.arange(40001,dtype=float),[a for a,b in points]])
                self.assertLess(np.max(abs(p.evaluate(t,s)-p.evaluate_independent(t,s))),1e-12)
                result=old.stage(t,p.evaluate(t,s),p.evaluate(t-700,dict(s,input_slew_ps=20)),s,ideal_input=True)
                self.assertEqual(result['pulse_counts']['rise']['input'],8)
                self.assertEqual(result['pulse_counts']['fall']['input'],8)
                self.assertTrue(result['input_timing_stimulus_passed'])

    def test_ideal_input_roundoff_retains_raw_values_and_output_gates(self):
        s=self.spec();t,vin,out,result=self.stage_result(s)
        raw=deepcopy(result['banks']['first']['timing'])
        actual=p.apply_reference(result,t,vin,s)
        self.assertTrue(actual['banks']['first']['timing']['measured_input_contract_passed'])
        self.assertTrue(actual['two_bank_zero_pilot_passed'])
        self.assertEqual(actual['banks']['first']['timing']['maximum_input_slew_ps'],raw['maximum_input_slew_ps'])
        witness=independent.stage(t,vin,out,s,ideal_input=True)
        other=deepcopy(actual);other['banks']['first']['timing']=witness
        other=p.apply_reference(other,t,vin,s,independent=True)
        self.assertTrue(same(actual,other))
        invalid=deepcopy(actual);invalid['banks']['first']['timing']['zero_code_quarter_passed']=False
        self.assertFalse(p.apply_reference(invalid,t,vin,s)['two_bank_zero_pilot_passed'])

    def test_known_source_guard_cannot_mask_real_slew_or_native_input_failure(self):
        s=self.spec();t,vin,out,result=self.stage_result(s)
        mismatch=vin.copy();mismatch[2100]+=.001
        self.assertFalse(p.apply_reference(deepcopy(result),t,mismatch,s)['two_bank_zero_pilot_passed'])
        too_slow=deepcopy(result);too_slow['banks']['first']['timing']['input_slews_10_90_ps']['rise'][0]=250.01
        self.assertFalse(p.apply_reference(too_slow,t,vin,s)['two_bank_zero_pilot_passed'])
        native_bad=deepcopy(result);native_bad['banks']['next']['bank_screen_passed']=False
        actual=p.apply_reference(native_bad,t,vin,s)
        self.assertFalse(actual['two_bank_zero_pilot_passed'])
        self.assertFalse(actual['banks']['next']['bank_screen_passed'])
