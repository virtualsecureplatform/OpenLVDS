# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic metrology checks only; these waveforms are not circuit evidence."""
import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import counter_protocol_300 as p
import counter_pvt_300_v1 as campaign

class Counter300Tests(unittest.TestCase):
    def waves(self, mhz=290,duty=.6,stop=0):
        t=np.arange(40001,dtype=float);period=1e6/mhz;points=[(0.,0.)]
        for k in range(7):
            start=2000+k*period;points += [(start,0.),(start+100,1.8)]
            if k<6 or stop==0:points += [(start+duty*period,1.8),(start+duty*period+100,0.)]
        pulse=lambda points:np.interp(t,*zip(*points))
        signals={'RCLK':pulse(points),'CLK':pulse([(x+200,y) for x,y in points])}
        req=[(0,0),(3390,0),(3410,1.8),(27990,1.8),(28010,0),(31990,0),(32010,1.8)]
        signals['REQUEST']=pulse(req);signals['XD:XR:request_i']=pulse([(x+200,y) for x,y in req])
        rise=lambda k:2250+k*period
        fall=lambda k:2250+k*period+duty*period
        assertions={'low0':fall(0)+150,'high1':rise(1)+150,'low1':fall(1)+150,
                    'armed':fall(2)+150,'PREPARE':rise(2)+150,'RESET_N':rise(3)+150}
        for name,event in assertions.items():
            values=[(0,0),(event-10,0),(event+10,1.8),(28500,1.8),(28520,0)]
            if name=='low0' and stop==0:values += [(32800,0),(32820,1.8)]
            signals[name if name in ('PREPARE','RESET_N') else 'XD:XR:'+name]=pulse(values)
        return t,signals,dict(mhz=mhz,duty=duty,stop_level=stop)
    def test_all_eighteen_clock_duty_stopped_protocols(self):
        for f in (290,300,310):
            for d in (.4,.5,.6):
                for level in (0,1):
                    t,v,s=self.waves(f,d,level);r=p.timing(t,v.__getitem__,s)
                    self.assertTrue(r['timing_protocol_passed'],(f,d,level,r))
                    self.assertEqual(r['clock_edges_before_transition'],dict(prepare=2,public_release=3))
    def test_incomplete_capture_rejected(self):
        t,v,s=self.waves()
        with self.assertRaises(ValueError):p.timing(t[:26001],lambda n:v[n][:26001],s)
    def test_wrong_frequency_and_missing_late_clock_rejected(self):
        t,v,s=self.waves()
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,dict(s,mhz=310))
        v['CLK'][t>21000]=0
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,s)
    def test_wrong_raw_duty_rejected(self):
        t,v,s=self.waves()
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,dict(s,duty=.4))
    def test_stopped_clock_reassertion_cannot_release_outputs(self):
        t,v,s=self.waves();v['RESET_N'][t>33000]=1.8
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,s)
    def test_wrong_clear_or_low_phase_rejected(self):
        t,v,s=self.waves();v['XD:XR:armed'][t>30000]=1.8
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,s)
        t,v,s=self.waves();v['XD:XR:low0']=v['XD:XR:high1'].copy()
        with self.assertRaises(ValueError):p.timing(t,v.__getitem__,s)
    def test_full_new_270_matrix_has_no_legacy_clock(self):
        specs=campaign.specifications()
        self.assertEqual(len(specs),270)
        self.assertEqual(len({json.dumps(s,sort_keys=True) for s in specs}),270)
        self.assertEqual({s['mhz'] for s in specs},{290,300,310})
        self.assertEqual(len({(s['process'],s['temperature']) for s in specs}),15)
        self.assertIsNone(campaign.assess([]))
    def test_fresh_fixture_delays_clear_until_all_clock_events_finish(self):
        parent=json.loads((campaign.PARENT/'manifest.json').read_text())['identity']
        for level in (0,1):
            spec=dict(campaign.specifications()[0],mhz=290,duty=.6,stop_level=level)
            text=campaign.fixture(p.policy.ROOT/'build/unused-counter-300',spec,parent['devices'][p.pilot.VARIANT])
            self.assertIn('.tran 1p 40n 0 1p',text)
            self.assertIn(p.REQUEST,text)
            self.assertNotIn('20.99n',text)
            self.assertIn('VDD VDD 0 1.8',text)
            self.assertIn('22.6896551724138n',text)
        with self.assertRaises(ValueError):
            campaign.fixture(p.policy.ROOT/'build/unused-counter-300',dict(spec,mhz=410),[])
