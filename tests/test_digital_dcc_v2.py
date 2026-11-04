# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_digital_dcc_v2 as dcc

class DCCMeasurementTests(unittest.TestCase):
    def wave(self, missing=False, glitch=False):
        t=np.arange(0,47001,1.)
        names=['time']+['v('+n+')' for n in ['p0','p180','q','xd.a','xd.b','xd.events','xd.feedback','xd.areset','xd.breset','vdd']]
        w=np.zeros((len(t),len(names)));w[:,0]=t*1e-12
        p0=2000+np.arange(19)*2500;p1=p0+1250
        source=np.sort(np.r_[p0,p1]);q=np.zeros(len(t))
        for i,a in enumerate(source):
            if missing and i==10:continue
            q[t>=a+200]=1.8*((i+1)%2)
        if glitch:q[(t>=15000+600)&(t<15000+650)]=1.8-q[(t>=15000+600)&(t<15000+650)]
        def pulse(edges,width):
            v=np.zeros(len(t))
            for a in edges:v[(t>=a)&(t<a+width)]=1.8
            return v
        values=[pulse(p0,750),pulse(p1,750),q,pulse(p0+50,200),pulse(p1+50,200),
                pulse(source+100,200),1.8-q,np.ones(len(t))*1.8,np.ones(len(t))*1.8,np.ones(len(t))*1.8]
        for i,v in enumerate(values,1):w[:,i]=v
        return names,w

    def test_exact_events_pass_but_not_physical_admission(self):
        with patch.object(dcc,'read_raw',return_value=self.wave()):
            result=dcc.measure(Path('/fixture'),dict(mhz=400,phase_error_ps=0))
        self.assertTrue(result['event_integrity_passed'])
        self.assertTrue(result['symmetric_timing_passed'])
        self.assertFalse(result['qualified_phy'])

    def test_dropped_event_and_extra_transition_rejected(self):
        for wave in [self.wave(missing=True),self.wave(glitch=True)]:
            with patch.object(dcc,'read_raw',return_value=wave):
                result=dcc.measure(Path('/fixture'),dict(mhz=400,phase_error_ps=0))
            self.assertFalse(result['event_integrity_passed'])

    def test_incomplete_export_cannot_pass(self):
        names,w=self.wave()
        with patch.object(dcc,'read_raw',return_value=(names,w[:1000])):
            with self.assertRaises(ValueError):dcc.measure(Path('/fixture'),dict(mhz=400,phase_error_ps=0))
