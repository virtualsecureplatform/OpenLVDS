# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_native_static_dcc_v2 as pilot
import measure_native_static_dcc_v2 as analysis


class NativeStaticDccTests(unittest.TestCase):
    def test_joint_deck_connects_early_data_prepare_and_keeps_public_mask_separate(self):
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            for spec in pilot.specifications():
                deck=pilot.fixture(Path('/fixture'),spec,[])
                self.assertIn('XR0 P0 REQUEST PREPARE_0 RESET_N VDD 0 '+pilot.components.release.NAME,deck)
                self.assertIn('XR180 P180 REQUEST PREPARE_180 RESET_180 VDD 0 '+pilot.components.release.NAME,deck)
                self.assertIn('XD 0 VDD Q P0 P180 RESET_N'+(' PREPARE_0' if spec['variant']=='prepare' else '')+' '+pilot.components.dcc_interface(spec['variant'])[0],deck)
                self.assertNotIn('VRESET',deck)
                probes=next(line.split()[2:] for line in deck.splitlines() if line.startswith('.print tran'))
                self.assertEqual(len(probes),len(set(probes)))
                self.assertTrue({'V(PREPARE_0)','V(PREPARE_180)'}<=set(probes))
        self.assertEqual({s['duty'] for s in pilot.specifications()},{.4,.6})

    def wave(self,early_mask=False,late_prepare=False,overstress=False,missing_output=False):
        p=1e6/410;origin=22000;t=np.arange(0,origin+22*p+1,.5)
        def clock(start):return np.where((t>=start)&((t-start)%p<.4*p),1.8,0)
        req=origin+3*p+150;mask0=origin+(5 if early_mask else 6)*p+250;mask180=mask0+p/2
        prep0=mask0+(100 if late_prepare else -p);prep180=mask180-p
        q=np.full(len(t),1.8);sources=[]
        for phase,offset in [('P0',100),('P180',100+p/2)]:
            for i in range(23):
                edge=origin+i*p+offset
                if edge>mask0:sources.append((edge,phase))
        for i,(edge,phase) in enumerate(sorted(sources)):
            if not missing_output or i!=3:q[t>=edge+250]=1.8 if phase=='P0' else 0
        if overstress:q[100]=2.1
        values={'p0':clock(origin+100),'p180':clock(origin+100+p/2),'q':q,'request':np.where(t>=req,1.8,0),
                'reset_n':np.where(t>=mask0,1.8,0),'reset_180':np.where(t>=mask180,1.8,0),
                'prepare_0':np.where(t>=prep0,1.8,0),'prepare_180':np.where(t>=prep180,1.8,0),'xf.vcm':np.full(len(t),.9)}
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t/1e12,*values.values()])

    def measure(self,**kw):
        ds=[dict(name='XD:test',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,terminals=['Q','P0','0','0'])]
        with patch.object(analysis,'validate',return_value=self.wave(**kw)):
            return analysis.measure(Path('/fixture'),pilot.specifications()[0],ds,'Test scope')

    def test_three_own_clock_edges_prepare_order_and_event_integrity_are_required(self):
        self.assertTrue(self.measure()['pilot_passed'])
        for kw,key in [(dict(early_mask=True),'reset_after_three_clock_edges_passed'),
                       (dict(late_prepare=True),'prepare_before_public_mask_passed'),
                       (dict(overstress=True),'terminal_screen_passed'),
                       (dict(missing_output=True),'event_integrity_passed')]:
            result=self.measure(**kw);self.assertFalse(result[key]);self.assertFalse(result['pilot_passed'])


if __name__=='__main__':unittest.main()
