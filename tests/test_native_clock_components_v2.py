# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_clock_components_v2 as components


class NativeClockComponentsTests(unittest.TestCase):
    def test_hierarchical_mapping_keeps_parasitic_body_nodes_distinct(self):
        text='.subckt cell A Y VGND VPWR\nX0 Y.t1 A.t0 VGND.t2 VGND.t3 sky130_fd_pr__nfet_01v8 w=1 l=.15\nR0 A A.t0 2\nC0 VGND.t3 VGND 2f\n.ends cell\n.subckt top CLK OUT GND VDD\nXu CLK OUT GND VDD cell\n.ends top\n'
        ds=components.mapped_mos(text,'top',dict(CLK='P0',OUT='Q',GND='0',VDD='VDD'),'XD')
        self.assertEqual(ds[0]['terminals'],['XD:Xu:Y.t1','XD:Xu:A.t0','XD:Xu:VGND.t2','XD:Xu:VGND.t3'])
        self.assertEqual(ds[0]['limit_v'],1.95)

    def test_native_port_order_is_mapped_by_name(self):
        rc={'cell':dict(info=dict(ports=['Y','VGND','A','VPWR']))}
        self.assertEqual(components.instance('u','cell',dict(A='CLK',Y='Q',VPWR='VDD',VGND='0'),rc),'Xu Q 0 CLK VDD cell')
        with self.assertRaises(ValueError):components.instance('u','cell',dict(A='CLK'),rc)

    def test_unknown_devices_and_recursive_hierarchy_are_rejected(self):
        for body in ['Bu A 0 V=1','Xu A top']:
            with self.assertRaises(ValueError):components.mapped_mos('.subckt top A\n'+body+'\n.ends top\n','top',dict(A='P0'),'XD')


if __name__=='__main__':unittest.main()
