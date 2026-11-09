# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_input_measure_300_v2 as p


class CompleteDCCInputTests(unittest.TestCase):
    def fixture(self):
        s=p.reference.specifications()[0]
        s=dict(s,r_slew_10_90_ps=20,f_slew_10_90_ps=250)
        stop=p.reference.capture_stop_ps(s)
        t=np.r_[np.arange(0,stop,1),stop]
        w=np.column_stack([t*1e-12,*[p.reference.evaluate(t,s,n) for n in ('P0','P180')]])
        return ['time','v(p0)','v(p180)'],w,s

    def test_complete_mixed_slew_and_wide_duty_clocks_reproduce_independently(self):
        names,w,s=self.fixture()
        for independent in (False,True):
            r=p.measure(names,w,s,independent=independent)
            self.assertTrue(r['input_contract_passed']);self.assertFalse(r['qualified_phy']);self.assertFalse(r['dcc_source_admitted'])
            self.assertEqual(r['clocks']['P0']['counts']['rise_0.9'],18)
            self.assertEqual(r['clocks']['P180']['counts']['fall_0.9'],18)
            self.assertLess(r['clocks']['P180']['maximum_slew_error_ps'],1e-6)

    def test_missing_first_event_last_fall_or_wrong_phase_cannot_pass(self):
        names,w,s=self.fixture();t=w[:,0]*1e12;period=1e6/s['mhz']
        bad=w.copy();bad[t<2100+period*.8,1]=0
        self.assertFalse(p.measure(names,bad,s)['input_contract_passed'])
        bad=w.copy();last_rise=2100+period/2+17*period
        bad[t>=last_rise,2]=1.8
        r=p.measure(names,bad,s,independent=True)
        self.assertFalse(r['input_contract_passed']);self.assertEqual(r['clocks']['P180']['counts']['fall_0.9'],17)
        bad=w.copy();bad[:,2]=p.reference.evaluate(t,dict(s,phase_error_ps=140),'P180')
        self.assertFalse(p.measure(names,bad,s)['phase_spacing_passed'])

    def test_incomplete_nonfinite_and_coarse_sampling_rejected(self):
        names,w,s=self.fixture()
        with self.assertRaisesRegex(ValueError,'complete'):p.measure(names,w[:-2],s)
        with self.assertRaisesRegex(ValueError,'DC'):p.measure(names,w[1:],s)
        bad=w.copy();bad[-1,1]=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'):p.measure(names,bad,s)
        indices=np.unique(np.r_[np.arange(0,len(w),4),len(w)-1])
        self.assertFalse(p.measure(names,w[indices],s)['input_contract_passed'])
