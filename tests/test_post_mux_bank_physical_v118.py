# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import post_mux_bank_physical_v118 as d


class PostMuxPhysicalGraphTests(unittest.TestCase):
    def fixture(self):
        cells=[dict(native_name='Xbank_regenerator',model=d.floor.INV,pins=dict(A='selected',Y='fine_slow',VPWR='VPWR',VGND='VGND')),
               dict(native_name='Xfine_compound',model=d.PAIR,pins=dict(A='fine_slow',Y='OUT',VPWR='VPWR',VGND='VGND')),
               dict(native_name='Xfine_unit0',model=d.FINE,pins=dict(A='fine_slow',CTRL='fine0',CTRL_B='fine_b0',VPWR='VPWR',VGND='VGND')),
               dict(native_name='Xtail_termination',model=d.original.TAIL,pins=dict(A='unused_tail',VGND='VGND'))]
        g=dict(ports=['IN','OUT','VPWR','VGND'],cells=cells)
        text='.subckt '+d.floor.INV+' A Y VPWR VGND\n.ends\n.subckt '+d.DRIVER+' IN OUT VPWR VGND\n.ends\n.subckt component_unit NODE EN ENB VDD VSS\n.ends\n.subckt component IN OUT VPWR VGND\nXbank_regenerator selected fine_slow VPWR VGND '+d.floor.INV+'\nXfine_compound fine_slow OUT VPWR VGND '+d.DRIVER+'\nXfine_unit0 fine_slow fine0 fine_b0 VPWR VGND component_unit\nXtail_termination unused_tail VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends component\n'
        return g,text

    def test_canonical_aliases_preserve_component_data_controls_and_bodies(self):
        g,text=self.fixture();r=d.compare_component(g,text,'component')
        self.assertEqual(r['components'],4);self.assertTrue(r['exact_component_calls_and_named_pins_verified'])
        self.assertFalse(r['qualified_phy'])

    def test_rejects_wrong_fine_data_body_tail_or_duplicate_component(self):
        g,text=self.fixture()
        for broken in [text.replace('Xfine_unit0 fine_slow','Xfine_unit0 OUT'),
                       text.replace('fine_b0 VPWR VGND component_unit','fine_b0 VGND VPWR component_unit'),
                       text.replace('w=2 l=2','w=3 l=2'),
                       text.replace('.ends component','Xfine_unit0 fine_slow fine0 fine_b0 VPWR VGND component_unit\n.ends component')]:
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):d.compare_component(g,broken,'component')

    def test_taller_fine_cell_must_preserve_all_global_control_and_supply_rails(self):
        old=dict(pins={p:dict(anchor_um=[.3,y]) for p,y in [('A',.2),('CTRL',8.6),('CTRL_B',9.4),('VPWR',10.3),('VGND',11.3)]})
        new=deepcopy(old)
        for p in new['pins'].values():p['anchor_um'][1]+=4.25
        self.assertEqual(d.fine_alignment(old,new),-4.25)
        new['pins']['CTRL']['anchor_um'][1]+=.1
        with self.assertRaisesRegex(ValueError,'align'):d.fine_alignment(old,new)
        del new['pins']['CTRL']
        with self.assertRaisesRegex(ValueError,'interface'):d.fine_alignment(old,new)


if __name__=='__main__':unittest.main()
