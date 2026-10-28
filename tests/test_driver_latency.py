# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_analog import driver_metrics


class DriverLatency(unittest.TestCase):
    def waveform(self,delay_ns,invert=False):
        t=np.arange(0,80e-9,5e-12);points=[(0,0.)]
        for i in range(62):
            at=(5+i*1.25)*1e-9;value=1.8*(i%2==0)
            points.extend([(at-20e-12,points[-1][1]),(at+20e-12,value)])
        pt,pv=np.array(points).T;inp=np.interp(t,pt,pv)
        out=.35*(2*np.interp(t-delay_ns*1e-9,pt,pv)/1.8-1)
        if invert:out=-out
        return np.column_stack([np.arange(len(t)),t,inp,1.25+out/2,1.25-out/2,np.full(len(t),1.4)])

    def test_delay_longer_than_one_ui_retains_polarity(self):
        result=driver_metrics(self.waveform(1.4),30)
        self.assertTrue(result['passed'],result)
        self.assertAlmostEqual(result['propagation_min_ps'],1400,places=4)
        self.assertAlmostEqual(result['propagation_max_ps'],1400,places=4)

    def test_inverting_driver_cannot_alias_into_a_valid_delay(self):
        result=driver_metrics(self.waveform(.15,invert=True),30)
        self.assertFalse(result['passed'])
        self.assertFalse(result['initial_polarity_ok'])
        self.assertFalse(result['polarity_ok'])

    def test_dropped_cycles_are_rejected(self):
        wave=self.waveform(1.4);mask=(wave[:,1]>40e-9)&(wave[:,1]<45e-9)
        wave[mask,3]=1.425;wave[mask,4]=1.075
        result=driver_metrics(wave,30)
        self.assertFalse(result['passed'])
        self.assertFalse(result['transitions_ok'])


if __name__=='__main__':unittest.main()
