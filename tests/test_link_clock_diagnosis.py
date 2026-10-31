# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_link_clock import pulse_transport


class ClockPulseDiagnosis(unittest.TestCase):
    def test_delayed_clock_preserves_all_interior_pulses(self):
        t=np.arange(0,30e-9,1e-12)
        signal=np.sin(2*np.pi*(t-.1e-9)/2.5e-9)
        output=1.8*(np.sin(2*np.pi*(t-.3e-9)/2.5e-9)>0)
        report=pulse_transport(t,signal,output,5e-9,25e-9)
        self.assertEqual(report['missing_output_edges'],0)
        self.assertGreater(len(report['pulses']),10)
        for pulse in report['pulses']: self.assertAlmostEqual(pulse['first_output_latency_ps'],200,delta=2)

    def test_absent_low_pulse_exposes_both_missing_polarities(self):
        t=np.arange(0,30e-9,1e-12)
        signal=np.sin(2*np.pi*(t-.1e-9)/2.5e-9)
        output=1.8*(np.sin(2*np.pi*(t-.3e-9)/2.5e-9)>0)
        output[(t>11.5e-9)&(t<13e-9)]=1.8
        report=pulse_transport(t,signal,output,5e-9,25e-9)
        self.assertEqual(report['rising_missing'],1)
        self.assertEqual(report['falling_missing'],1)
