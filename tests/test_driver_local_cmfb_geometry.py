# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from driver_local_cmfb_geometry import analog_first,relocate_bus,clear_bus_y
from driver_compact_geometry import via45
from layout import Geometry,GRID


class LocalCMFBGeometry(unittest.TestCase):
    def example(self):
        g=Geometry()
        for x,y in [(0.,-190.),(10.,-310.)]:
            g.wire('metal5',x,y,x,200.,1.6)
            via45(g,x,y);via45(g,x,200.)
        via45(g,0.,200.)  # same-net duplicate landing from shared columns
        g.wire('metal4',-2.,200.,12.,200.,.8)
        g.wire('metal4',-2.,210.,12.,210.,.8)
        return g

    def test_bus_and_all_duplicate_old_landings_move_but_terminals_remain(self):
        g=self.example();old=deepcopy(g.layers)
        result=relocate_bus(g,200.,-150.,[])
        self.assertEqual(result['columns'],2)
        self.assertIn(old['metal4'][-1],g.layers['metal4'])
        for layer in ['metal4','metal5','via4']:
            landing=Geometry();via45(landing,0.,200.)
            self.assertNotIn(landing.layers[layer][0],g.layers[layer])
            terminal=Geometry();via45(terminal,0.,-190.)
            self.assertIn(terminal.layers[layer][0],g.layers[layer])
        stems=[r for r in g.layers['metal5'] if r[2]-r[0]==round(1.6/GRID)]
        self.assertTrue(all(r[3]==round((-150.+.8)/GRID) for r in stems))

    def test_bus_may_not_cross_any_child_bounds(self):
        g=self.example();before=deepcopy(g.layers)
        with self.assertRaises(ValueError):relocate_bus(g,200.,-190.,[dict(bbox_um=[-5.,-200.,5.,-180.])])
        self.assertEqual(g.layers,before)

    def test_unrelated_parent_landing_is_avoided_even_outside_all_children(self):
        g=self.example();g.pad('metal4',5.,200.,1.8)
        before=deepcopy(g.layers)
        with self.assertRaises(ValueError):relocate_bus(g,200.,200.,[])
        self.assertEqual(g.layers,before)
        new=clear_bus_y(g,200.,[])
        self.assertEqual(new,197.)
        relocate_bus(g,200.,new,[])

    def test_original_nine_analog_groups_stay_together_without_losing_others(self):
        top='openlvds_driver_core'
        leaves=['__XCM__XNP_F0','__XCM__XNM_F0','__XCM__XNT_F0','__XCM__XPL_F0','__XCM__XPR_F0',
                '__XRCP','__XRCN','__XRCM0','__XRCM1']
        groups=[dict(name=top+'__OTHER')]+[dict(name=top+n) for n in reversed(leaves)]
        before=deepcopy(groups);result=analog_first(groups,top)
        self.assertEqual([d['name'] for d in result[:9]],[top+n for n in leaves])
        self.assertEqual(result[-1]['name'],top+'__OTHER')
        self.assertEqual(groups,before)
        with self.assertRaises(ValueError):analog_first(groups[:-1],top)
