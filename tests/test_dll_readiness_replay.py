# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_readiness_replay import input_events,clocked_health,replay


def trace(stop=2100,fault=False,unsafe=False,late_loss=False):
    t=np.arange(0,stop+0.005,0.005)*1e-9
    def clock(delay):
        points=[(0,0)]
        for at in np.arange(5+delay,stop+3,2.5):
            if late_loss and 2200<=at-delay<2300:continue
            points.extend([(at-.05,0),(at+.05,1.8),(at+1.2,1.8),(at+1.3,0)])
        return np.interp(t,np.array(points)[:,0]*1e-9,np.array(points)[:,1])
    bad=np.zeros(len(t))
    if fault:bad[(t>=1800e-9)&(t<1840e-9)]=1.8
    values=[clock(0),bad,clock(.05),clock(.675),clock(1.3),clock(1.41 if unsafe else 1.3),
            np.ones(len(t)),np.full(len(t),.47),np.full(len(t),.47)]
    names=['CLK','BAD','PH0','PH90','PD_REF','PH180','CTRL','UF','DF']
    return np.column_stack([np.arange(len(t)),t,*values]),{f'V({n})':i+2 for i,n in enumerate(names)}


class NativeReadiness(unittest.TestCase):
    def test_bad_pulses_between_clock_edges_are_not_discarded(self):
        wave,h=trace(stop=100)
        keep=(wave[:,1]>=50.1e-9)&(wave[:,1]<50.15e-9)
        wave[keep,h['V(BAD)']]=1.8
        events=input_events(wave,h)
        at=0;transitions=[];previous='0'
        for dt,bits in events:
            at+=dt
            if bits[2]!=previous:transitions.append(at*1e-6)
            previous=bits[2]
        self.assertEqual(len(transitions),2)
        self.assertTrue(all(50<value<51 for value in transitions))

    def test_locked_clock_health_rejects_phase_error_above_100ps(self):
        for unsafe in [False,True]:
            wave,h=trace(stop=100,unsafe=unsafe)
            result=clocked_health(wave,h,np.arange(50,90,2.5)*1e-9)
            self.assertEqual(result['passed'],not unsafe,result)

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus is in scripts/env.sh')
    def test_actual_rtl_asserts_only_after_native_phase_settles(self):
        with tempfile.TemporaryDirectory() as folder:
            result=replay(*trace(),Path(folder))
            self.assertTrue(result['passed'],result)
            self.assertGreater(result['assertions'][0]['at_ns'],1600)

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus is in scripts/env.sh')
    def test_unsafe_native_phase_does_not_pass_with_an_optimistic_bad_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            result=replay(*trace(unsafe=True),Path(folder))
            self.assertFalse(result['passed'])
            self.assertFalse(result['clocked_health']['passed'])

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus is in scripts/env.sh')
    def test_actual_rtl_requalifies_after_a_native_bad_fault(self):
        with tempfile.TemporaryDirectory() as folder:
            result=replay(*trace(stop=4000,fault=True),Path(folder))
            self.assertTrue(result['passed'],result)
            self.assertEqual(len(result['assertions']),2)
            self.assertGreater(result['assertions'][1]['at_ns'],3300)

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus is in scripts/env.sh')
    def test_late_clock_loss_clears_and_rearms_after_prior_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            result=replay(*trace(stop=4700,late_loss=True),Path(folder),recovery=True)
            self.assertTrue(result['passed'],result)
            self.assertTrue(result['clock_loss_requalified'])
            self.assertLess(result['assertions'][0]['at_ns'],2200)
            self.assertGreater(result['assertions'][1]['at_ns'],3900)
