# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_guarded_clock_prepare_v2 as pilot


class GuardedPreparePilotTests(unittest.TestCase):
    def raw(self,folder,spec,extra_release=False,stress=False):
        t=np.arange(0,26001,20,dtype=float);clk=np.zeros(len(t));period=1e6/spec['mhz']
        for i in range(7):
            start=2000+i*period
            clk[(t>=start)&((t<start+period*spec['duty']) if i<6 or not spec['stop_level'] else np.ones(len(t),dtype=bool))]=1.8
        request=np.where(((t>=3400)&(t<21000))|(t>=23000),1.8,0)
        prep=np.where((t>=7200)&(t<21060),1.8,0);mask=np.where((t>=9700)&(t<21200),1.8,0)
        if extra_release:mask[t>=23500]=1.8
        bad=np.where(t==23500,2.1 if stress else 0,0)
        names=['time','v(clk)','v(request)','v(prepare)','v(reset_n)','v(vdd)','v(xd.bad)']
        w=np.column_stack([t*1e-12,clk,request,prep,mask,np.full(len(t),1.8),bad])
        header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())

    def test_prepare_after_two_and_public_release_after_three_with_both_stop_levels(self):
        mos=[dict(name='test',terminals=['0','VDD','RESET_N','XD:bad'],limit_v=1.95)]
        for level in [0,1]:
            spec=dict(pilot.specifications()[0],stop_level=level)
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);self.raw(p,spec);r=pilot.measure(p,spec,mos)
            self.assertEqual(r['clock_edges_before_transition'],dict(prepare=2,public_release=3))
            self.assertTrue(r['stopped_clock_clear_and_reassert_passed']);self.assertTrue(r['counter_feasibility_passed'])
            self.assertFalse(r['qualified_phy'])

    def test_stopped_clock_reassertion_and_late_stress_cannot_be_hidden(self):
        spec=pilot.specifications()[0];mos=[dict(name='test',terminals=['0','VDD','RESET_N','XD:bad'],limit_v=1.95)]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.raw(p,spec,extra_release=True)
            with self.assertRaisesRegex(ValueError,'rising-event count'):pilot.measure(p,spec,mos)
            self.raw(p,spec,stress=True);r=pilot.measure(p,spec,mos)
            self.assertFalse(r['counter_feasibility_passed']);self.assertFalse(r['terminal_screen_passed'])


if __name__=='__main__':unittest.main()
