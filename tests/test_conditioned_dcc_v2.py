# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_conditioned_dcc_v2 as pilot
import measure_conditioned_dcc_v2 as analysis


class JointConditionedDccTests(unittest.TestCase):
    spec=dict(variant='p3',process='ss',temperature=40,mhz=410,load_ff=20,slew0_ps=100,slew180_ps=100,duty=.3,raw_start_ns=22)

    def wave(self,early=False,overstress=False):
        p=1e6/410;origin=22000;t=np.arange(0,origin+22*p+1,.5)
        def clock(start):return np.where((t>=start)&((t-start)%p<.3*p),1.8,0)
        req=origin+3*p+150;reset=origin+(4 if early else 5)*p+250
        q=np.full(len(t),1.8);sources=[]
        for phase,offset in [('P0',100),('P180',100+p/2)]:
            for i in range(23):
                edge=origin+i*p+offset
                if edge>reset:sources.append((edge,phase))
        for edge,phase in sorted(sources):q[t>=edge+250]=1.8 if phase=='P0' else 0
        if overstress:q[100]=2.1
        values={'p0':clock(origin+100),'p180':clock(origin+100+p/2),'q':q,'reset_n':np.where(t>=reset,1.8,0),
                'request':np.where(t>=req,1.8,0),'xf.vcm':np.full(len(t),.9),'vddio':np.full(len(t),3.3)}
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t/1e12,*values.values()])

    def measure(self,**kw):
        ds=[dict(name='XD:test',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,terminals=['Q','P0','0','0']),
            dict(name='XB:test',model='sky130_fd_pr__pfet_g5v0d10v5',limit_v=5.5,terminals=['VDDIO','0','0','0'])]
        with patch.object(analysis,'read_raw',return_value=self.wave(**kw)):return analysis.measure(Path('/fixture'),self.spec,ds,'Test scope')

    def test_actual_post_request_clock_edges_and_voltage_domains_are_checked(self):
        result=self.measure();self.assertTrue(result['pilot_passed']);self.assertFalse(result['qualified_phy'])
        self.assertTrue(result['reset_after_two_clock_edges_passed']);self.assertAlmostEqual(result['terminal_abs_peak_v'],3.3)
        self.assertFalse(self.measure(early=True)['reset_after_two_clock_edges_passed'])
        self.assertFalse(self.measure(overstress=True)['terminal_screen_passed'])

    def test_reset_is_clock_driven_and_only_request_is_an_external_stimulus(self):
        with patch.dict(os.environ,PDK_ROOT='/pdk'):deck=pilot.fixture(Path('/fixture'),self.spec,[])
        self.assertIn('XR0 P0 REQUEST RESET_N VDD 0 '+pilot.release.NAME,deck)
        self.assertIn('XR180 P180 REQUEST RESET_180 VDD 0 '+pilot.release.NAME,deck)
        self.assertIn('VREQUEST REQUEST 0 PWL',deck)
        self.assertNotIn('VR RESET_N',deck)
        self.assertIn('XD 0 VDD Q P0 P180 RESET_N '+pilot.sizing.circuit.NAME,deck)


if __name__=='__main__':unittest.main()
