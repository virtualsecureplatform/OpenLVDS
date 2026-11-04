# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_clock_release_v2 as release


class StaticClockReleaseTests(unittest.TestCase):
    def test_async_internal_clear_and_two_new_edges_after_clock_stop(self):
        cells=release.gates()
        for stop_level in [0,1]:
            values={p['Y']:None for _,_,p in cells}
            def settle(clk,request):
                nonlocal values
                for _ in range(40):
                    old=dict(values,CLK=clk,REQUEST=request);updates={}
                    for _,model,p in cells:
                        if model.startswith('inv_'):out=None if old[p['A']] is None else 1-old[p['A']]
                        else:
                            args=[old[p[n]] for n in ['A','B']+(['C'] if model.startswith('nand3_') else [])]
                            out=1 if 0 in args else (0 if all(v==1 for v in args) else None)
                        updates[p['Y']]=out
                    values=updates
            settle(0,0);self.assertEqual(values['RESET_N'],0)
            settle(0,1);settle(1,1);self.assertEqual(values['RESET_N'],0)
            settle(0,1);settle(1,1);self.assertEqual(values['RESET_N'],1)
            settle(stop_level,1);settle(stop_level,0)
            for n in ['r0_q','r1_q','r0_m','r1_m']:self.assertEqual(values[n],0)
            self.assertEqual(values['RESET_N'],0)
            settle(stop_level,1);self.assertEqual(values['RESET_N'],0)
            settle(0,1);settle(1,1);self.assertEqual(values['RESET_N'],0)
            settle(0,1);settle(1,1);self.assertEqual(values['RESET_N'],1)

    def test_native_reset_gates_and_strong_output_are_real_devices(self):
        library=''
        for model in ['nand2_2','nand2_4','nand3_2','inv_1','inv_8']:
            inputs=['A'] if model.startswith('inv_') else ['A','B']+(['C'] if model.startswith('nand3_') else [])
            ports=' '.join([*inputs,'VGND','VNB','VPB','VPWR','Y'])
            library+=f'.subckt sky130_fd_sc_hd__{model} {ports}\nX0 Y A private VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        text=release.source(library)
        self.assertEqual(len(release.gates()),24)
        self.assertEqual(text.count('w=.65 l=.15'),24)
        self.assertIn('w=4 l=4',text)
        self.assertEqual(sum(m=='nand3_2' and p['C']=='REQUEST' for _,m,p in release.gates()),4)
        self.assertNotIn('.ic',text)


if __name__=='__main__':unittest.main()
