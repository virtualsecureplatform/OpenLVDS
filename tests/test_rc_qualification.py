# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rc_certificate import REQUIRED,valid
from validate_fast import compare
from spice_engine import engine,provenance

class Qualification(unittest.TestCase):
    def test_partial_and_stale_certificates_are_rejected(self):
        runner=Path(__file__).resolve().parents[1]/'scripts/validate_fast.py'
        c=dict(passed=True,complete_suite=True,cases={k:dict(passed=True) for k in REQUIRED},
               runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),fast_inputs={'a':'b'},
               simulator=engine(),simulator_provenance=provenance())
        self.assertTrue(valid(c,{'a':'b'}))
        self.assertFalse(valid(c,{'a':'changed'}))
        c['cases'].pop('driver');self.assertFalse(valid(c,{'a':'b'}))

    def test_identical_inactive_dll_does_not_qualify(self):
        time=np.linspace(0,1500e-9,15001)
        wave=np.column_stack([np.arange(len(time)),time,np.zeros((len(time),3))])
        a=('dll','full',wave,{},{});b=('dll','fast',wave.copy(),{},{})
        self.assertFalse(compare('dll',a,b)['passed'])

    def test_comparison_detects_edge_displacement(self):
        time=np.linspace(0,60e-9,12001)
        def waveform(shift):
            # Smooth edges let interpolation resolve shifts below the grid.
            v=.9+.9*np.tanh(np.sin(2*np.pi*(time-shift)/2.5e-9)*20)
            return np.column_stack([np.arange(len(time)),time,v])
        a=('receiver','full',waveform(0),{},{})
        self.assertTrue(compare('receiver',a,('receiver','fast',waveform(0),{},{}))['passed'])
        self.assertFalse(compare('receiver',a,('receiver','fast',waveform(50e-12),{},{}))['passed'])

if __name__=='__main__':unittest.main()
