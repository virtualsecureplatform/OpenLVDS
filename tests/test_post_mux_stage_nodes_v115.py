# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_post_mux_stages_v115 as stages


class PostMuxStageNodesTests(unittest.TestCase):
    def bank(self):
        tg='.subckt tg A Z EN ENB VPWR VGND\nRin A a0 2\nRout Z z0 3\nXn z0 EN a0 VGND sky130_fd_pr__nfet_01v8 w=.42 l=.15\n.ends tg\n'
        inv='.subckt inv A Y VGND VPWR\nRin A g 2\nRslow Y slow 10\nRfast Y fast 1\nXn fast g VGND VGND sky130_fd_pr__nfet_01v8 w=.42 l=.15\nXp slow g VPWR VPWR sky130_fd_pr__pfet_01v8 w=.84 l=.15\n.ends inv\n'
        top='.subckt bank IN OUT VPWR VGND\nXswitch0_0_0 IN tree0_0 E EB VPWR VGND tg\nXswitch0_0_1 tap1 tree0_0 E EB VPWR VGND tg\nXswitch1_0_0 tree0_0 selected E EB VPWR VGND tg\nXbank_regenerator selected fine_slow VGND VPWR inv\nXfine_driver fine_slow OUT VGND VPWR inv\n.ends bank\n'
        return tg+inv+top

    def test_uses_actual_post_mux_inversions_and_nearest_saved_native_terminals(self):
        points=stages.stage_nodes(self.bank(),'bank',1);p={x['stage']:x for x in points}
        self.assertEqual(p['first_mux_input']['node'],'XD:Xswitch0_0_1:a0')
        self.assertFalse(p['root_mux_output']['inverted'])
        self.assertTrue(p['common_regenerator_output']['inverted'])
        self.assertEqual(p['common_regenerator_output']['node'],'XD:Xbank_regenerator:fast')
        self.assertEqual(p['common_regenerator_output']['representative_wire_resistance_ohm'],1.)
        self.assertTrue(p['final_inverter_input']['inverted'])
        self.assertFalse(p['output']['inverted'])

    def test_rejects_nonpositive_resistance_and_disconnected_saved_terminals(self):
        with self.assertRaisesRegex(ValueError,'Nonpositive'):
            stages.stage_nodes(self.bank().replace('Rfast Y fast 1','Rfast Y fast 0'),'bank',0)
        with self.assertRaisesRegex(ValueError,'No saved'):
            stages.stage_nodes(self.bank().replace('Rin A a0 2','Rin lost a0 2'),'bank',0)


if __name__=='__main__':unittest.main()
