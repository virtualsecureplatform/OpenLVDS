# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_source_measure_300_v2 as p
import test_dcc_input_measure_300_v2 as input_fixture


class CompleteDCCSourceTests(unittest.TestCase):
    def fixture(self,phase_error=0,extra_f_delay=0):
        names,w,s=input_fixture.CompleteDCCInputTests().fixture()
        s=dict(s,phase_error_ps=phase_error);t=w[:,0]*1e12
        # Keep the complete tail long enough for either permitted phase offset.
        stop=p.inputs.reference.capture_stop_ps(s)
        t=np.r_[np.arange(0,stop,1),stop];values={'time':t*1e-12}
        for n in ('P0','P180'):values['v('+n.lower()+')']=p.inputs.reference.evaluate(t,s,n)
        sources={};falls={}
        for node in ('p0','p180'):
            v=values['v('+node+')'];sources[node]=p.inputs.edge_times(t,v,.9,True,False);falls[node]=p.inputs.edge_times(t,v,.9,False,False)
        def pulse(up,down):return 1.8*np.minimum(np.clip(.5+(t-up)/20,0,1),np.clip(.5-(t-down)/20,0,1))
        for node,tag in (('p0','a'),('p180','b')):
            values['v(xd.'+tag+')']=sum(pulse(x+60,x+180) for x in sources[node])
            reset=np.full(len(t),1.8)
            for x,y in zip(sources[node],falls[node]):reset-=pulse(x+100,y+40)
            values['v(xd.'+tag+'reset)']=reset
        events=np.sort(np.r_[sources['p0'],sources['p180']])
        values['v(xd.events)']=sum(pulse(x+80,x+200) for x in events)
        q=np.full(len(t),1.8)
        for k,x in enumerate(events):
            delay=120+(extra_f_delay if k%2 else 0)
            q+=(-1 if k%2==0 else 1)*1.8*np.clip(.5+(t-x-delay)/40,0,1)
        values['v(q)']=q;values['v(vdd)']=np.full(len(t),1.8)
        names=list(values);return names,np.column_stack(list(values.values())),s

    def test_complete_startup_and_last_pulses_pass_both_readers(self):
        names,w,s=self.fixture()
        for independent in (False,True):
            r=p.measure(names,w,s,independent=independent)
            self.assertTrue(r['source_screen_passed']);self.assertEqual(len(r['event_checks']),36);self.assertEqual(len(r['pulse_checks']),36)
            self.assertTrue(all(c['nonempty_hold_window'] for c in r['pulse_checks']))
            self.assertFalse(r['physical_source_admitted']);self.assertFalse(r['qualified_phy'])

    def test_unchanged_output_cannot_hide_missing_startup_pulse_or_premature_reset(self):
        names,w,s=self.fixture();t=w[:,0]*1e12
        bad=w.copy();bad[t<2600,names.index('v(xd.a)')]=0
        r=p.measure(names,bad,s);self.assertFalse(r['source_screen_passed']);self.assertFalse(r['pulse_generator_integrity_passed'])
        bad=w.copy();bad[(t>2500)&(t<2700),names.index('v(xd.areset)')]=1.8
        r=p.measure(names,bad,s,independent=True);self.assertFalse(r['source_screen_passed']);self.assertFalse(r['pulse_checks'][0]['passed'])

    def test_balanced_half_cycle_limit_and_intentional_spacing_error_are_distinct(self):
        names,w,s=self.fixture(extra_f_delay=80)
        r=p.measure(names,w,s);self.assertFalse(r['symmetric_timing_passed']);self.assertFalse(r['source_screen_passed'])
        names,w,s=self.fixture(phase_error=140,extra_f_delay=80)
        r=p.measure(names,w,s,independent=True)
        self.assertFalse(r['balanced_half_cycle_required']);self.assertIsNone(r['symmetric_timing_passed']);self.assertTrue(r['source_screen_passed'])


    def test_valid_slow_output_can_begin_during_input_ramp_before_input_midpoint(self):
        names,w,s=self.fixture();s=dict(s,r_slew_10_90_ps=250)
        t=w[:,0]*1e12
        for node,phase in (('p0','P0'),('p180','P180')):
            w[:,names.index('v('+node+')')]=p.inputs.reference.evaluate(t,s,phase)
        sources=np.sort(np.r_[p.inputs.edge_times(t,w[:,names.index('v(p0)')],.9,True,False),
                              p.inputs.edge_times(t,w[:,names.index('v(p180)')],.9,True,False)])
        q=np.full(len(t),1.8)
        for k,x in enumerate(sources):q+=(-1 if k%2==0 else 1)*1.8*np.clip(.5+(t-x-120)/(248/.8),0,1)
        w[:,names.index('v(q)')]=q
        # Output midpoint still follows the input midpoint, but a valid slow
        # edge starts earlier. Only the pre-stimulus interval is initial idle.
        self.assertLess(q[np.argmin(abs(t-2100))],1.62)
        for independent in (False,True):self.assertTrue(p.measure(names,w,s,independent=independent)['source_screen_passed'])
