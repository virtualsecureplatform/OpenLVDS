# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_phase_clock_release_v2 as release


class PhaseArmedReleaseTests(unittest.TestCase):
    def settle(self,cells,values,**inputs):
        for _ in range(80):
            old=dict(values,VPWR=1,**inputs);new={}
            for _,model,p in cells:
                if model.startswith('inv_'):v=None if old[p['A']] is None else 1-old[p['A']]
                else:
                    args=[old[p[k]] for k in ['A','B']+(['C'] if model.startswith('nand3_') else [])]
                    v=1 if 0 in args else 0 if all(a==1 for a in args) else None
                new[p['Y']]=v
            values=new
        return values

    def test_readiness_arriving_in_high_phase_waits_for_low_then_high(self):
        cells=release.phase_gates();v={p['Y']:None for _,_,p in cells}
        def step(clk,request,ready):
            nonlocal v
            v=self.settle(cells,v,CLK=clk,REQUEST=request,r1_q=ready)
        step(1,0,0);step(1,1,1);self.assertEqual(v['RESET_N'],0)
        step(0,1,1);self.assertEqual(v['armed'],1);self.assertEqual(v['RESET_N'],0)
        step(1,1,1);self.assertEqual(v['RESET_N'],1)
        step(0,1,0);self.assertEqual(v['RESET_N'],1)
        for level in [0,1]:
            step(level,0,0);self.assertEqual(v['RESET_N'],0);self.assertEqual(v['armed'],0)

    def test_readiness_and_arm_states_clear_with_stopped_clock(self):
        cells=release.gates()
        for stop in [0,1]:
            v={p['Y']:None for _,_,p in cells}
            def step(clk,request):
                nonlocal v
                v=self.settle(cells,v,CLK=clk,REQUEST=request)
            step(0,0);step(0,1)
            for edge in range(2):
                step(1,1);self.assertEqual(v['RESET_N'],0);step(0,1)
            step(1,1);self.assertEqual(v['RESET_N'],1)
            step(stop,0)
            for n in ['r0_q','r1_q','r0_m','r1_m','armed','RESET_N']:self.assertEqual(v[n],0)
            step(stop,1);self.assertEqual(v['RESET_N'],0)


if __name__=='__main__':unittest.main()
