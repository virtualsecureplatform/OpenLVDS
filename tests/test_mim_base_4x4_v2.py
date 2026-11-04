# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mim_base_4x4_v2 as base
import restrict_macro_rails_v3 as access
import layout


class SharedBaseTests(unittest.TestCase):
    def test_shared_shunt_is_one_native_4x4_mim_with_two_ports(self):
        ports,devices=layout.flatten(layout.circuits(base.schematic()),base.NAME)
        self.assertEqual(ports,['NODE','VSS']);self.assertEqual(len(devices),1)
        self.assertEqual(devices[0]['model'],'sky130_fd_pr__cap_mim_m3_1')
        self.assertEqual(devices[0]['nodes'],['NODE','VSS'])
        self.assertEqual(devices[0]['params'],dict(w='4',l='4'))

    def test_raw_lef_without_obstructions_gains_hidden_plate_obstructions(self):
        text=('MACRO shunt\n  ORIGIN 0 -0.1 ;\n  SIZE 9 BY 9 ;\n'
            '  PIN NODE\n    PORT\n      LAYER met3 ;\n        RECT 0 7 8 7.4 ;\n'
            '      LAYER met4 ;\n        RECT 1 1 5 5 ;\n    END\n  END NODE\n'
            '  PIN VSS\n    PORT\n      LAYER met3 ;\n        RECT 0 8 8 8.6 ;\n'
            '        RECT 1 1 6 6 ;\n    END\n  END VSS\nEND shunt\nEND LIBRARY\n')
        ports=dict(NODE=dict(x_um=.3,y_um=7.2),VSS=dict(x_um=.3,y_um=8.3))
        result,pins=access.restrict(text,ports,dict(NODE=('INPUT','SIGNAL'),VSS=('INOUT','GROUND')))
        self.assertEqual(access.geometry.geometry(text),access.geometry.geometry(result))
        self.assertEqual(len(list(access.geometry.OBS.finditer(result))),1)
        self.assertIn('  ORIGIN 0 -0.1 ;\n  SIZE 9 BY 9 ;',result)
        self.assertTrue(all([layer for layer,_ in access.geometry.rectangles(p[2])]==['met3'] for p in access.geometry.PIN.finditer(result)))
        self.assertEqual(pins['VSS']['use'],'GROUND')
        with self.assertRaisesRegex(ValueError,'declared macro interface'):access.restrict(text,{},dict(NODE=('INPUT','SIGNAL')))
