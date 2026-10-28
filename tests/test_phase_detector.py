# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_phase_detector import metrics


class PhaseErrorResponse(unittest.TestCase):
    def wave(self,bad,offset=0):
        t=np.linspace(0,40e-9,8001)
        w=np.zeros((len(t),8));w[:,0]=np.arange(len(t));w[:,1]=t
        w[:,2]=1.8*(np.mod(t-5e-9,2.5e-9)<1.25e-9)
        w[:,3]=1.8*(np.mod(t-5e-9-offset*1e-12,2.5e-9)<1.25e-9)
        w[:,7]=bad
        return w

    def test_stuck_low_cannot_qualify_error_detection(self):
        self.assertTrue(metrics(self.wave(0),0)['passed'])
        self.assertFalse(metrics(self.wave(0,150),150)['passed'])
        self.assertFalse(metrics(self.wave(0,-150),-150)['passed'])

    def test_valid_error_high_and_quiet_locked_output(self):
        self.assertTrue(metrics(self.wave(1.8,300),300)['passed'])
        self.assertFalse(metrics(self.wave(1.8,50),50)['passed'])
        self.assertFalse(metrics(self.wave(.8,300),300)['passed'])

    def test_missing_input_clock_cannot_qualify_a_quiet_flag(self):
        wave=self.wave(0);wave[:,2:4]=0
        self.assertFalse(metrics(wave,0)['passed'])

    def test_incomplete_transient_is_rejected(self):
        self.assertFalse(metrics(self.wave(1.8)[:-20],150)['passed'])

    def test_two_fault_edges_per_reference_cycle_are_rejected(self):
        wave=self.wave(0,150);phase=np.mod(wave[:,1],2.5e-9)
        wave[:,7]=1.8*((phase<.3e-9)|((phase>.6e-9)&(phase<.9e-9)))
        self.assertFalse(metrics(wave,150)['passed'])

    def test_narrow_fault_high_is_rejected(self):
        wave=self.wave(0,150)
        wave[:,7]=1.8*(np.mod(wave[:,1],2.5e-9)<.1e-9)
        self.assertFalse(metrics(wave,150)['passed'])


if __name__=='__main__':unittest.main()
