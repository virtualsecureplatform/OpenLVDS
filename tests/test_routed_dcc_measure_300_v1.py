# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import routed_dcc_measure_300_v1 as p
from replay_bank_300_v2 import same


class RoutedDCCMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f=p.fixture;info=json.loads((f.proof.PARENT/'extraction.json').read_text());text=(f.proof.ROOT/info['netlist']).read_text()
        s=f.waveform.specifications()[0];_,obs=f.fixture(Path('unused-routed-dcc'),s,info,text)
        stop=f.waveform.capture_stop_ps(s);t=np.r_[np.arange(0,stop,1),stop];values={'time':t*1e-12}
        canonical=lambda n:'v('+n.replace(':','.').lower()+')'
        release=f.release_ps(s)
        values['v(vdd)']=np.full(len(t),1.8);values['v(reset_n)']=1.8*np.clip((t-release+10)/20,0,1)
        events=[];rises={};falls={}
        for phase in ('P0','P180'):
            values[canonical(phase)]=f.waveform.evaluate(t,s,phase)
            period,first,high,full=f.waveform.parameters(s,phase)
            rises[phase]=np.array([first+k*period for k in range(18) if first+k*period>release])
            falls[phase]=rises[phase]+high;events += [(x,phase) for x in rises[phase]]
        events.sort()
        def pulse(up,down):return 1.8*np.minimum(np.clip(.5+(t-up)/20,0,1),np.clip(.5-(t-down)/20,0,1))
        for phase,tag,clear in (('P0','pulse0','clear0'),('P180','pulse180','clear180')):
            values[canonical(obs['signals'][tag])]=sum(pulse(x+60,x+180) for x in rises[phase])
            reset=values['v(reset_n)'].copy()
            for x,y in zip(rises[phase],falls[phase]):reset-=pulse(x+100,y+40)
            values[canonical(obs['signals'][clear])]=reset
        values[canonical(obs['signals']['events'])]=sum(pulse(x+80,x+200) for x,n in events)
        q=np.full(len(t),1.8)
        for k,(x,n) in enumerate(events):q+=(-1 if k%2==0 else 1)*1.8*np.clip(.5+(t-x-120)/40,0,1)
        values['v(q)']=q
        for d in obs['devices']+obs['passive_resistors']:
            for n in d['terminals']:
                if n!='0':values.setdefault(canonical(n),np.zeros(len(t)))
        cls.names=list(values);cls.w=np.column_stack(list(values.values()));cls.s=s;cls.obs=obs

    def test_all_active_events_phase_zero_and_native_stress_agree(self):
        a=p.measure(self.names,self.w,self.s,self.obs);b=p.measure(self.names,self.w,self.s,self.obs,independent=True)
        self.assertTrue(same(a,b));self.assertTrue(a['routed_point_passed']);self.assertTrue(a['phase0_delivery_passed'])
        self.assertEqual(len(a['event_checks']),29);self.assertEqual(len(a['pulse_checks']),29)
        self.assertEqual(len(a['terminal_stress']),192);self.assertFalse(a['actual_release_circuit_qualified']);self.assertFalse(a['qualified_phy'])

    def test_complemented_clock_or_internal_dc_stress_cannot_pass(self):
        bad=self.w.copy();bad[:,self.names.index('v(q)')]=1.8-bad[:,self.names.index('v(q)')]
        r=p.measure(self.names,bad,self.s,self.obs);self.assertFalse(r['phase0_delivery_passed']);self.assertFalse(r['routed_point_passed'])
        node=next(n for d in self.obs['devices'] for n in d['terminals'] if n.startswith('XD:') and n not in self.obs['signals'].values())
        bad=self.w.copy();bad[0,self.names.index('v('+node.replace(':','.').lower()+')')]=2.1
        for independent in (False,True):
            r=p.measure(self.names,bad,self.s,self.obs,independent=independent)
            self.assertFalse(r['native_terminal_stress_passed']);self.assertFalse(r['routed_point_passed'])

    def test_late_reset_arming_and_missing_full_capture_rejected(self):
        bad=self.w.copy();event=next(x for x,n in sorted((float(x),phase) for phase in ('P0','P180')
            for x in p.inputs.edge_times(self.w[:,0]*1e12,self.w[:,self.names.index('v('+phase.lower()+')')],.9,True,False))
            if n=='P0' and x>p.fixture.release_ps(self.s))
        node='v('+self.obs['signals']['clear0'].replace(':','.').lower()+')'
        k=np.argmin(abs(self.w[:,0]*1e12-(event-30)));bad[k,self.names.index(node)]=0
        r=p.measure(self.names,bad,self.s,self.obs,independent=True)
        self.assertTrue(r['phase0_delivery_passed']);self.assertFalse(r['pulse_generator_integrity_passed']);self.assertFalse(r['routed_point_passed'])
        with self.assertRaises(ValueError):p.measure(self.names,self.w[:-2],self.s,self.obs)
        with self.assertRaisesRegex(ValueError,'terminal observations'):
            p.measure([n+'bad' if n==node else n for n in self.names],self.w,self.s,self.obs)
