# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_digital_dcdl_v2 as dcdl

class DCDLMeasurements(unittest.TestCase):
    def wave(self,extra=False,early=False):
        t=np.arange(40001,dtype=float)
        def pulse(start,end):
            return 1.8*np.clip((t-start+10)/20,0,1)*np.clip((end+10-t)/20,0,1)
        source=pulse(2100,20100)
        out=pulse(1100 if early else 3100,21200)
        if extra:out=np.maximum(out,pulse(25000,26000))
        return ['time','v(in)','v(out)'],np.column_stack([t*1e-12,source,out])

    def test_unwrapped_delay_not_modulo_clock(self):
        with patch.object(dcdl,'read_raw',return_value=self.wave()):
            r=dcdl.measure(Path('/fixture'))
        self.assertAlmostEqual(r['rise_delay_ps'],1000)
        self.assertAlmostEqual(r['fall_delay_ps'],1100)
        self.assertAlmostEqual(r['rise_slew_ps'],16)
        self.assertFalse(r['qualified_phy'])

    def test_extra_pulse_and_wrong_epoch_rejected(self):
        for w in [self.wave(extra=True),self.wave(early=True)]:
            with patch.object(dcdl,'read_raw',return_value=w):
                with self.assertRaises(ValueError):dcdl.measure(Path('/fixture'))

    def test_partial_raw_never_scored(self):
        names,w=self.wave()
        with patch.object(dcdl,'read_raw',return_value=(names,w[:22000])):
            with self.assertRaises(ValueError):dcdl.measure(Path('/fixture'))
