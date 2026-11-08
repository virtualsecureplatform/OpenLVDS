# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capture_openpll_long_300 as p

class LongClockTests(unittest.TestCase):
    def original(self):return (p.BASE/'bench.cir').read_text()
    def test_pilot_changes_only_sparse_linear_solver(self):
        original=self.original();pilot=p.deck(original,70)
        self.assertEqual(pilot.replace('\n.option klu','',1),original)
    def test_long_capture_retains_bias_models_and_step_extends_reset_hold(self):
        original=self.original();long=p.deck(original,20000)
        self.assertIn('.tran 2.0p 20000.0n 0 2.0p',long)
        self.assertIn('VRESET RESET_N 0 PULSE(0 {VDD} 5.0n 50p 50p 20000.0n 40000.0n)',long)
        undo=long.replace('\n.option klu','',1).replace('20000.0n 40000.0n','70.0n 140.0n').replace('.tran 2.0p 20000.0n','.tran 2.0p 70.0n')
        self.assertEqual(undo,original)
    def test_absolute_waveform_parity_rejects_phase_or_voltage_difference(self):
        t=np.linspace(0,70e-9,35001);a=.9+.9*np.sin(2*np.pi*300e6*t+.3)
        self.assertTrue(p.parity(t,a,t,a)['passed'])
        b=.9+.9*np.sin(2*np.pi*300e6*(t-5e-12)+.3)
        self.assertFalse(p.parity(t,a,t,b)['passed'])
        self.assertFalse(p.parity(t,a,t,a+.005)['passed'])
    def test_partial_or_nonfinite_reference_cannot_qualify_solver(self):
        t=np.linspace(0,70e-9,35001);a=.9+.9*np.sin(2*np.pi*300e6*t+.3)
        with self.assertRaises(ValueError):p.parity(t[:-10],a[:-10],t,a)
        a[50]=np.nan
        with self.assertRaises(ValueError):p.parity(t,a,t,a)
    def test_changed_tolerances_repeated_solver_or_unbounded_duration_rejected(self):
        original=self.original()
        with self.assertRaises(ValueError):p.deck(original.replace('reltol=1e-3','reltol=1e-2'),70)
        with self.assertRaises(ValueError):p.deck(p.deck(original,70),70)
        with self.assertRaises(ValueError):p.deck(original,200001)
        with self.assertRaises(ValueError):p.prepare(70)
