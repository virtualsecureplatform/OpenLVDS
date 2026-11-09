# SPDX-License-Identifier: GPL-3.0-only
import itertools
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_input_waveforms_300_v2 as p
from regenerated_bank_periodic_measure_v67 import crossings


class DCCInputWaveformTests(unittest.TestCase):
    def base(self):return p.specifications()[0]

    def test_exact_independent_duty_slew_and_pvt_coverage(self):
        specs=p.specifications();self.assertEqual(len(specs),4860)
        self.assertEqual(len({json.dumps(s,sort_keys=True) for s in specs}),4860)
        self.assertEqual({(s['r_duty'],s['f_duty']) for s in specs},set(itertools.product((.4,.5,.6),repeat=2)))
        self.assertEqual({(s['r_slew_10_90_ps'],s['f_slew_10_90_ps']) for s in specs},set(itertools.product((20,250),repeat=2)))
        self.assertEqual(len({(s['process'],s['temperature'],s['mhz']) for s in specs}),45)

    def test_all_startup_edges_have_declared_slew_duty_and_phase(self):
        for rd,fd,rs,fs,e in itertools.product((.4,.6),(.4,.6),(20,250),(20,250),(-140,0,140)):
            s=dict(self.base(),r_duty=rd,f_duty=fd,r_slew_10_90_ps=rs,f_slew_10_90_ps=fs,phase_error_ps=e)
            rises={}
            for phase,key in (('P0','r'),('P180','f')):
                rows=p.points(s,phase);t=np.asarray([x for x,v in rows]);v=np.asarray([v for x,v in rows])
                rise=crossings(t,v,.9,True);fall=crossings(t,v,.9,False);rises[phase]=np.asarray(rise)
                self.assertEqual(len(rise),18);self.assertEqual(len(fall),18)
                np.testing.assert_allclose(np.asarray(fall)-rise,s[key+'_duty']*1e6/s['mhz'],rtol=0,atol=1e-8)
                for up in (True,False):
                    a=np.asarray(crossings(t,v,.18,up));b=np.asarray(crossings(t,v,1.62,up))
                    np.testing.assert_allclose(abs(b-a),s[key+'_slew_10_90_ps'],rtol=0,atol=1e-8)
                sample=np.unique(np.r_[t,(t[1:]+t[:-1])/2])
                np.testing.assert_allclose(p.evaluate(sample,s,phase),p.evaluate(sample,s,phase,independent=True),rtol=0,atol=1e-9)
                self.assertEqual(v[0],0);self.assertEqual(v[-1],0)
                self.assertGreaterEqual(t[-1]-rows[-2][0],1000-1e-8)
            np.testing.assert_allclose(rises['P0'],2100+np.arange(18)*1e6/s['mhz'],rtol=0,atol=1e-8)
            np.testing.assert_allclose(rises['P180']-rises['P0'],.5e6/s['mhz']+e,rtol=0,atol=1e-8)

    def test_actual_fixture_changes_only_two_clock_sources_duration_and_title(self):
        s=dict(self.base(),f_slew_10_90_ps=20,phase_error_ps=140);out=p.previous.ROOT/'build/unused-dcc-input-test'
        old=p.previous.fixture(out,p.seed_spec(s));new=p.fixture(out,s)
        def unchanged(text):
            lines=text.splitlines()[1:];result=[];skipping=False
            for line in lines:
                if line.startswith(('VP0 ','VP1 ')):
                    skipping='PWL(' in line;continue
                if skipping:
                    if line=='+ )':skipping=False
                    continue
                if line.startswith('.tran '):continue
                result.append(line)
            return result
        self.assertEqual(unchanged(old),unchanged(new))
        self.assertTrue(new.startswith('OpenLVDS '+p.VERSION))
        self.assertIn('.tran 1p ',new)
        # Both wide phases require a finite-source tail beyond the old stop.
        self.assertGreater(p.capture_stop_ps(s),2000+18e6/s['mhz'])

    def test_outside_profile_and_unknown_phase_refused(self):
        for patch in (dict(r_slew_10_90_ps=16),dict(f_slew_10_90_ps=200),dict(cycles=17),dict(temperature=80)):
            with self.subTest(patch=patch),self.assertRaisesRegex(ValueError,'Undeclared'):p.points(dict(self.base(),**patch),'P0')
        with self.assertRaisesRegex(ValueError,'Unknown'):p.points(self.base(),'other')
