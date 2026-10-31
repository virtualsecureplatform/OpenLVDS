# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_rx_publication import groups


class NativePublicationProbes(unittest.TestCase):
    def source(self):
        rows=[]
        for pin in ['data[0]','data[1]','valid']:
            for depth in range(3):
                node=pin if depth==0 else pin+'_g'+str(depth-1)
                gate=pin+'_g'+str(depth)
                rows += [f'R{len(rows)} {node} {node}.t0 3',
                    f'X{len(rows)} {node}.t0 {gate} VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15',
                    # Opposite D/S orientation must select the same signal.
                    f'X{len(rows)+1} VPWR {gate} {node}.t0 VPWR sky130_fd_pr__pfet_01v8_hvt w=2 l=.15']
        rows += ['Xclk clock_bar clk VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15']
        return '\n'.join(rows)

    def test_native_rc_terminals_are_saved_without_treating_supply_as_signal(self):
        result=groups(self.source())
        self.assertEqual(result['data[0]_stage_0'],['data[0].t0'])
        self.assertEqual(result['data[0]_gate_0'],['data[0]_g0'])
        self.assertEqual(result['data[0]_stage_2'],['data[0]_g1.t0'])
        self.assertEqual(result['valid_supply_0'],['VGND','VPWR'])
        self.assertEqual(result['CLK_LOCAL_GATES'],['clk'])
        self.assertEqual(result['CLK_CONTROLLED_SIGNALS'],['clock_bar'])

    def test_missing_output_or_supply_short_prevents_probe_preparation(self):
        with self.assertRaisesRegex(ValueError,'No native output driver'):
            groups(self.source().replace('data[1]','unknown'))
        with self.assertRaisesRegex(ValueError,'supply'):
            groups(self.source()+'\nRshort data[0] VPWR 1')
