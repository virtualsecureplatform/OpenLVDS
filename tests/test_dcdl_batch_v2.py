# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_cap_strong_v2 as policy
import probe_digital_dcdl_batch_v2 as batch

class DenseDCDLTests(unittest.TestCase):
    def data(self,extra=False,bad_control=False):
        t=np.arange(0,20001,10,dtype=float)
        names=['time','v(in)','v(out)','v(xd.f0)','v(xd.r0)','v(vdd)']+[f'v(xd.cap{i})' for i in range(31)]+[f'v({n.lower()})' for i in range(31) for n in (f'E{i}',f'EB{i}')]
        w=np.zeros((len(t),len(names)));w[:,0]=t*1e-12
        def pulse(a,b):return 1.8*np.clip((t-a+20)/40,0,1)*np.clip((b+20-t)/40,0,1)
        w[:,1]=pulse(2100,6100)+pulse(12100,16100)
        w[:,2]=pulse(2600,6600)+pulse(12610,16610)
        if extra:w[:,2]+=pulse(18000,18500)
        w[:,3]=w[:,1];w[:,4]=w[:,2];w[:,5]=1.8
        for i in range(31):
            w[:,names.index(f'v(e{i})')]=np.where((t>=10000)&(i==0),1.8,0)
            w[:,names.index(f'v(eb{i})')]=1.8-w[:,names.index(f'v(e{i})')]
        if bad_control:w[t==13000,names.index('v(e0)')]=0
        return names,w
    def task(self):
        return dict(spec=dict(coarse=0,codes=[0,1]),devices=policy.circuit(0)[1])
    def test_each_pulse_is_unwrapped_and_controls_are_qualified(self):
        with patch.object(batch.h,'read_raw',return_value=self.data()):result=batch.measure(Path('/fixture'),self.task())
        self.assertAlmostEqual(result['samples'][0]['rise_delay_ps'],500)
        self.assertAlmostEqual(result['samples'][1]['rise_delay_ps'],510)
        self.assertTrue(result['custom_mos_stress_passed'])
        self.assertFalse(result['qualified_phy'])
    def test_extra_transition_and_unsettled_control_rejected(self):
        for data in [self.data(extra=True),self.data(bad_control=True)]:
            with patch.object(batch.h,'read_raw',return_value=data):
                with self.assertRaises(ValueError):batch.measure(Path('/fixture'),self.task())
    def test_early_partial_batch_cannot_qualify_completed_prefix(self):
        names,w=self.data()
        with patch.object(batch.h,'read_raw',return_value=(names,w[:1800])):
            with self.assertRaises(ValueError):batch.measure(Path('/fixture'),self.task())
