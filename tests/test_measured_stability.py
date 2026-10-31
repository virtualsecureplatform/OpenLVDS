# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from measure_dll_stability import settling_time,pulse_train,instrument_source


class MeasuredStability(unittest.TestCase):
    def test_instrumentation_only_exposes_an_existing_node(self):
        source='.subckt openlvds_dll_analog A VSS\nC0 CTRL.t1 VSS 4p\n.ends\n.subckt lvds_bias PB NB VP VN\n.ends\n'
        result=instrument_source(source,'CTRL.t1')
        self.assertIn('.subckt openlvds_dll_analog A VSS CTRL.t1',result)
        self.assertIn('C0 CTRL.t1 VSS 4p',result)
        with self.assertRaises(ValueError):instrument_source(source,'nonexistent')

    def test_settling_requires_staying_in_the_band(self):
        t=np.arange(6,dtype=float)
        values=np.array([0,.95,1.2,1.01,1.,1.])
        self.assertEqual(settling_time(t,values,1.),3)
        with self.assertRaises(ValueError):settling_time(t,values,0.)

    def test_validation_step_waits_for_acquisition(self):
        text=pulse_train(3300,390)
        words=text.split('PWL(',1)[1].split(')',1)[0].split()
        points=[(float(words[i][:-1]),float(words[i+1])) for i in range(0,len(words),2)]
        rises=np.array([at-.05 for at,value in points if value==1.8 and at<1800 and any(abs(at-(5+k*2.5+.05))<1e-6 for k in range(680))])
        self.assertTrue(np.any(abs(rises-1697.5)<1e-6))
        self.assertIn('1700.05n 1.8',text)
        self.assertIn('1702.61410256n 1.8',text)
