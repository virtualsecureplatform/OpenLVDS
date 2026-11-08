# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_dcc_source_300 as replay


def waveform():
    t=np.arange(0,65002,2.);period=1e6/300;duty=.6
    def pulse(delay,width):
        phase=(t-delay)%period
        return np.minimum(np.clip(phase/20,0,1),np.clip((width+20-phase)/20,0,1))*1.8
    p0=pulse(2000,period*duty);p1=pulse(2000+period/2,period*(1-duty))
    a=pulse(2050,200);b=pulse(2050+period/2,200)
    times=[0.];values=[0.];level=0.
    for at in sorted([2000+period*k+100 for k in range(20)]+[2000+period/2+period*k+100 for k in range(20)]):
        times.extend([at,at+20]);values.extend([level,1.8-level]);level=1.8-level
    q=np.interp(t,times,values)
    names=['time','v(p0)','v(p180)','v(q)','v(xd.events)','v(xd.a)','v(xd.b)','v(xd.areset)','v(xd.breset)']
    w=np.column_stack([t*1e-12,p0,p1,q,np.maximum(a,b),a,b,np.zeros_like(t),np.zeros_like(t)])
    return names,w,dict(mhz=300,duty=duty,phase_error_ps=0)


class ReplayTests(unittest.TestCase):
    def test_native_event_and_duty_screen(self):
        names,w,spec=waveform();result=replay.independent(names,w,spec)
        self.assertTrue(result['independent_source_screen_passed'])
        self.assertLess(result['mean_half_cycle_error_ps'],.02)

    def test_missing_outputs_wrong_duty_and_released_hold_rejected(self):
        names,w,spec=waveform()
        bad=w.copy();bad[:,names.index('v(q)')]=0
        self.assertFalse(replay.independent(names,bad,spec)['independent_source_screen_passed'])
        self.assertFalse(replay.independent(names,w,dict(spec,duty=.4))['independent_source_screen_passed'])
        bad=w.copy();bad[:,names.index('v(xd.areset)')]=1.8
        self.assertFalse(replay.independent(names,bad,spec)['independent_source_screen_passed'])

    def test_partial_and_nonfinite_raw_rejected(self):
        names,w,spec=waveform()
        with self.assertRaises(ValueError):replay.independent(names,w[:-2000],spec)
        w[10,3]=np.nan
        with self.assertRaises(ValueError):replay.independent(names,w,spec)

    def test_incomplete_campaign_cannot_receive_matrix_admission(self):
        with tempfile.TemporaryDirectory() as name,patch.object(replay.producer,'bound',return_value={}):
            parent=Path(name);(parent/'state.json').write_text(json.dumps(dict(status='running',qualified_phy=False)))
            with self.assertRaises(ValueError):replay.replay(parent,[],full=True)
            with self.assertRaises(ValueError):replay.replay(parent,['0','0'])


if __name__=='__main__':unittest.main()
