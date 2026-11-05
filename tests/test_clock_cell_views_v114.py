# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_clock_cell_views_v114 as views


class CanonicalReferenceTests(unittest.TestCase):
    def test_aliases_parent_nets_without_changing_child_pin_names_or_device_parameters(self):
        text='.subckt child NODE EN VDD VSS\nXcore NODE VDD NODE VDD native w=1.26 l=.15 ad=.3654 as=.3654 pd=3.1 ps=3.1\n.ends child\n.subckt fine NODE EN ENB VDD VSS\nXswitch NODE EN fine__CAP VSS child\nXcap fine__CAP ENB VDD VSS child\n.ends fine\n'
        result=views.reference(text,'fine','canonical',views.FINE_ALIASES)
        self.assertEqual(result.split('.subckt canonical')[0],text.split('.subckt fine')[0])
        self.assertIn('.subckt canonical A CTRL CTRL_B VPWR VGND',result)
        self.assertIn('Xswitch A CTRL fine__CAP VGND child',result)
        self.assertIn('Xcap fine__CAP CTRL_B VPWR VGND child',result)
        self.assertIn('.ends canonical',result)

    def test_rejects_missing_port_or_nonbijective_aliases(self):
        text='.subckt fine NODE EN ENB VDD VSS\n.ends fine\n'
        with self.assertRaisesRegex(ValueError,'interface'):
            views.reference(text,'fine','canonical',dict(NODE='A'))
        bad=dict(views.FINE_ALIASES,EN='A')
        with self.assertRaisesRegex(ValueError,'bijective'):
            views.reference(text,'fine','canonical',bad)


if __name__=='__main__':unittest.main()
