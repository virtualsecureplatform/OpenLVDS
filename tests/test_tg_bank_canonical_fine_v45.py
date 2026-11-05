# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_bank_physical_netlist_v45 as view


class CanonicalFineInterfaceTests(unittest.TestCase):
    def inputs(self):
        cells=(f'.subckt {view.FINE} NODE EN ENB VDD VSS\n'
               'XN NODE EN cap VSS sky130_fd_pr__nfet_01v8 w=.42 l=.15 ad=.1 as=.2 pd=1 ps=2\n'
               'XP cap ENB NODE VDD sky130_fd_pr__pfet_01v8 w=.84 l=.15 ad=.2 as=.4 pd=2 ps=4\n'
               'XR cap ENB VSS VSS sky130_fd_pr__nfet_01v8 w=.42 l=.15 ad=.1 as=.2 pd=1 ps=2\n'
               f'XC cap VSS {view.MIM} w=2 l=3\nXG ENB VSS {view.MIM} w=2 l=2\n.ends {view.FINE}\n')
        ports=['IN','OUT',*[f'S{i}' for i in range(4)],*[f'E{i}' for i in range(31)],'VPWR','VGND']
        bank=f'.subckt {view.SOURCE} '+' '.join(ports)+f'\nXfine_unit0 OUT E0 E1 VPWR VGND {view.FINE}\nXtail_termination unused_tail VGND {view.MIM} w=2 l=2\n.ends {view.SOURCE}\n'
        tail=f'.subckt {view.TAIL} A VGND\nXC A VGND {view.MIM} w=2 l=2\n.ends {view.TAIL}\n'
        return cells,bank,tail

    def test_real_legacy_interface_gets_canonical_pin_names_and_roles(self):
        g=view.graph(*self.inputs());fine=g['cells'][0]
        self.assertEqual(g['orders'][view.FINE],['A','CTRL','CTRL_B','VPWR','VGND'])
        self.assertEqual(fine['pins'],dict(A='OUT',CTRL='E0',CTRL_B='E1',VPWR='VPWR',VGND='VGND'))
        for p in ('A','VPWR','VGND'):self.assertEqual(view.direction(view.FINE,p),'inout')
        for p in ('CTRL','CTRL_B'):self.assertEqual(view.direction(view.FINE,p),'input')

    def test_native_fine_aliases_preserve_body_ties_and_all_six_primitives(self):
        cells,bank,tail=self.inputs();g=view.graph(cells,bank,tail)
        native,report=view.native_view(cells,bank,tail,g)
        self.assertEqual(report['native_primitives'],6);self.assertTrue(report['exact_native_connectivity_and_parameters_preserved'])
        ports,body=view.native.definitions(native)[view.FINE]
        self.assertEqual(ports,['A','CTRL','CTRL_B','VPWR','VGND'])
        self.assertEqual(body[0][1:5],['A','CTRL','cap','VGND'])
        self.assertEqual(body[1][1:5],['cap','CTRL_B','A','VPWR'])
        self.assertEqual(body[-1][1:3],['CTRL_B','VGND'])

    def test_emitted_blackbox_exposes_power_and_capacitive_roles(self):
        g=view.graph(*self.inputs());text=view.blackboxes(g)
        for s in ('inout wire A','inout wire VPWR','inout wire VGND','input wire CTRL','input wire CTRL_B'):self.assertIn(s,text)
        self.assertNotIn('wire VDD',text);self.assertNotIn('wire VSS',text)
        self.assertEqual(g['physical_pin_aliases'][view.FINE],view.FINE_ALIASES)


if __name__=='__main__':unittest.main()
