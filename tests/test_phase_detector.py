# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_phase_detector import metrics,pulse_metrics,response_cases,library_ports


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

    def test_fault_cadence_can_be_measured_after_analog_settling(self):
        wave=self.wave(1.8,150)
        time=wave[:,1]+100e-9
        response=pulse_metrics(time,wave[:,2],wave[:,7],120e-9,140e-9)
        self.assertTrue(response['passed'])
        self.assertGreater(response['reference_cycles'],5)
        self.assertFalse(pulse_metrics(time,wave[:,2],wave[:,7])['passed'])

    def long_wave(self):
        t=np.linspace(0,160e-9,160001);w=np.zeros((len(t),8));w[:,0]=np.arange(len(t));w[:,1]=t
        w[:,2]=1.8*(np.mod(t-5e-9,2.5e-9)<1.25e-9)
        w[:,3]=1.8*(np.mod(t-5.15e-9,2.5e-9)<1.25e-9)
        w[:,7]=1.8*(t>100e-9)
        return w

    def test_settled_window_accepts_late_fault_but_rejects_startup_only_fault(self):
        wave=self.long_wave()
        self.assertTrue(metrics(wave,150,120e-9,160e-9)['passed'])
        self.assertFalse(metrics(wave,150)['passed'])
        wave[:,7]=1.8-wave[:,7]
        self.assertFalse(metrics(wave,150,120e-9,160e-9)['passed'])

    def test_long_window_requires_complete_transient(self):
        self.assertFalse(metrics(self.long_wave()[:-20],150,120e-9,160e-9)['passed'])

    def test_phase_matrices_cover_process_temperature_and_slew(self):
        self.assertEqual(len(response_cases()),7)
        corners=response_cases(corners=True);slews=response_cases(slew_corners=True)
        self.assertEqual(len(set(corners)),105)
        self.assertEqual(len(set(slews)),70)
        self.assertEqual({(r[3],r[4]) for r in slews},{(20,200),(200,20)})

    def test_pin_binding_reads_exact_subcircuit_and_continuations(self):
        lib=b'.subckt lvds_pfd_physical WRONG\n.ends\n.subckt lvds_pfd REF FB\n+ QREF QFB QWIN\n.ends\n'
        self.assertEqual(library_ports(lib,'lvds_pfd'),['REF','FB','QREF','QFB','QWIN'])
        with self.assertRaises(ValueError):library_ports(lib,'missing')


if __name__=='__main__':unittest.main()
