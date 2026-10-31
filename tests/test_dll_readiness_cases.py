# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from qualify_dll_readiness import clock_wave,loss_fixture,STOP_NS


class LateLossFixture(unittest.TestCase):
    def test_clock_loss_follows_initial_acquisition_and_leaves_time_to_relock(self):
        words=clock_wave().split('PWL(',1)[1].split(')',1)[0].split()
        points=np.array([(float(words[i][:-1])/1000,float(words[i+1])) for i in range(0,len(words),2)])
        rises=points[(points[:,1]==1.8)&np.r_[False,points[:-1,1]==0],0]-.05
        self.assertIn(2197.5,rises);self.assertIn(2300,rises)
        self.assertFalse(np.any((rises>=2200)&(rises<2300)))
        self.assertGreater(STOP_NS-2380,615*2.5+500)
        self.assertTrue(np.all(np.diff(rises[(rises>2300)&(rises<4600)])==2.5))

    def test_native_detector_rearm_matches_rtl_precharge_and_loads(self):
        body,probes=loss_fixture('ss',0,{'CTRL':['ctrl_terminal']})
        self.assertIn('2210.02n 0 2380.2n 0 2380.22n 1.8',body)
        self.assertIn('C0 PH0 0 40f',body);self.assertIn('C90 PH90 0 40f',body)
        self.assertEqual(probes['CTRL'],'XL:XCORE:XA:ctrl_terminal')
