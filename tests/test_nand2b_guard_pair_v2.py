# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nand2b_guard_pair_v2 as pair
import restrict_macro_rails_v5 as access


class GuardPairTests(unittest.TestCase):
    def test_pair_maps_the_actual_child_pin_order_without_touching_native_source(self):
        original='.subckt '+pair.CHILD+' A_N B Y VPWR VGND\nXgate Y A_N B VGND native w=.65 l=.15\n.ends\n'
        text=pair.schematic(original)
        self.assertTrue(text.startswith(original))
        self.assertIn('Xleft A_N B Y VPWR VGND '+pair.CHILD,text)
        self.assertIn('Xright A_N B Y VPWR VGND '+pair.CHILD,text)
        self.assertEqual(text.count('w=.65 l=.15'),1)
        with self.assertRaises(ValueError):pair.schematic(original.replace(' VPWR VGND',' VPWR private'))

    def test_m4_access_preserves_every_routing_shape_and_rejects_wrong_layer(self):
        text='MACRO pair\n  PIN Y\n    DIRECTION OUTPUT ;\n    USE SIGNAL ;\n    PORT\n      LAYER met3 ;\n        RECT 0 0 10 0.4 ;\n      LAYER met4 ;\n        RECT 0 1 10 1.4 ;\n    END\n  END Y\nEND pair\n'
        ports=dict(Y=dict(layer='metal4',x_um=.3,y_um=1.2));types=dict(Y=('OUTPUT','SIGNAL'))
        changed,view=access.restrict(text,ports,types)
        self.assertEqual(view['Y']['layer'],'met4')
        self.assertEqual(access.geometry.geometry(changed),access.geometry.geometry(text))
        for point in [dict(layer='metal2',x_um=.3,y_um=1.2),dict(layer='metal4',x_um=.3,y_um=.2)]:
            with self.assertRaises(ValueError):access.restrict(text,dict(Y=point),types)


if __name__=='__main__':unittest.main()
