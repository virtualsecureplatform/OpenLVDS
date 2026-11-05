# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_bank_physical_netlist_v42 as view


class PhysicalTGGraphTests(unittest.TestCase):
    def inputs(self):
        cells=(f'.subckt {view.INV} A Y VGND VPWR\n'
               'XN Y A VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15 ad=.1 as=.1 pd=1 ps=1\n'
               'XP Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15 ad=.2 as=.2 pd=2 ps=2\n'
               f'XC Y VGND {view.MIM} w=2 l=2\n.ends {view.INV}\n'
               f'.subckt {view.SC}buf_4 A VGND VNB VPB VPWR X\n'
               'XN X A VGND VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15 ad=.1 as=.1 pd=1 ps=1\n'
               'XP X A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=.15 ad=.2 as=.2 pd=2 ps=2\n'
               f'.ends {view.SC}buf_4\n')
        ports=['IN','OUT',*[f'S{i}' for i in range(4)],*[f'E{i}' for i in range(31)],'VPWR','VGND']
        bank=(f'.subckt {view.SOURCE} '+' '.join(ports)+'\n'+
              f'Xinput_inverse IN tap0 VGND VPWR {view.INV}\n'+
              f'Xfine_driver tap0 OUT VGND VPWR {view.INV}\n'+
              f'Xtail_load tap0 VGND VGND VPWR VPWR unused_tail {view.SC}buf_4\n'+
              f'Xtail_termination unused_tail VGND {view.MIM} w=2 l=2\n.ends {view.SOURCE}\n')
        tail=f'.subckt {view.TAIL} A VGND\nXC A VGND {view.MIM} l=2 w=2\n.ends {view.TAIL}\n'
        return cells,bank,tail

    def imported(self,g):
        names=sorted(set(g['ports'])|{n for c in g['cells'] for n in c['pins'].values()})
        scalar={n:i+2 for i,n in enumerate(names)}
        ports={p:dict(direction='inout' if p in view.RAILS else 'output' if p=='OUT' else 'input',bits=[scalar[p]]) for p in g['ports']}
        cells={c['name']:dict(type=c['model'],parameters={},attributes=dict(keep='1',dont_touch='1'),
                             connections={p:[scalar[n]] for p,n in c['pins'].items()},
                             port_directions={p:view.direction(c['model'],p) for p in c['pins']}) for c in g['cells']}
        modules={view.NAME:dict(ports=ports,cells=cells,netnames={n:dict(bits=[b]) for n,b in scalar.items()})}
        for model,pins in g['orders'].items():
            modules[model]=dict(attributes=dict(blackbox='1'),cells={},
                                ports={p:dict(direction=view.direction(model,p),bits=[i+2]) for i,p in enumerate(pins)})
        return dict(modules=modules)

    def test_explicit_pin_mapping_preserves_body_ties_and_tail_load(self):
        g=view.graph(*self.inputs());tail=next(c for c in g['cells'] if c['model']==view.TAIL)
        self.assertEqual(tail['pins'],dict(A='unused_tail',VGND='VGND'))
        buffer=next(c for c in g['cells'] if c['name']=='u_tail_load')
        self.assertEqual(buffer['pins']['VNB'],'VGND');self.assertEqual(buffer['pins']['VPB'],'VPWR')
        self.assertEqual(buffer['pins']['X'],'unused_tail')
        self.assertIn('.VPB(VPWR)',view.verilog(g))

    def test_native_only_view_preserves_every_primitive_and_parameter(self):
        cells,bank,tail=self.inputs();g=view.graph(cells,bank,tail)
        native,report=view.native_view(cells,bank,tail,g)
        self.assertTrue(report['exact_native_connectivity_and_parameters_preserved'])
        self.assertEqual(report['native_primitives'],9);self.assertEqual(report['native_model_counts'][view.MIM],3)
        changed=native.replace('tap0 VGND VGND VPWR VPWR unused_tail','tap0 VGND VGND VGND VPWR unused_tail',1)
        self.assertNotEqual(view.signature(native,view.NAME),view.signature(changed,view.NAME))

    def test_wrong_tail_parameter_attachment_and_missing_tail_are_rejected(self):
        cells,bank,tail=self.inputs()
        for before,after in [('w=2 l=2','w=3 l=2'),('Xtail_termination unused_tail VGND','Xtail_termination tap0 VGND')]:
            with self.subTest(fault=before),self.assertRaises(ValueError):view.graph(cells,bank.replace(before,after,1),tail)
        missing='\n'.join(l for l in bank.splitlines() if not l.startswith('Xtail_termination '))+'\n'
        with self.assertRaises(ValueError):view.graph(cells,missing,tail)

    def test_passive_and_transmission_gate_signal_pins_remain_bidirectional(self):
        for model,pin in [(view.TAIL,'A'),(view.TG,'A'),(view.TG,'Z'),(view.FINE,'A')]:
            self.assertEqual(view.direction(model,pin),'inout')
        self.assertEqual(view.direction(view.TG,'EN'),'input');self.assertEqual(view.direction(view.INV,'Y'),'output')

    def test_import_rejects_body_miswire_and_dropped_tail(self):
        g=view.graph(*self.inputs());data=self.imported(g)
        self.assertTrue(view.verify_json(data,g)['exact_native_component_graph_verified'])
        bad=deepcopy(data);m=bad['modules'][view.NAME]
        m['cells']['u_tail_load']['connections']['VPB']=m['netnames']['VGND']['bits']
        with self.assertRaises(ValueError):view.verify_json(bad,g)
        bad=deepcopy(data);del bad['modules'][view.NAME]['cells']['u_tail_termination']
        with self.assertRaises(ValueError):view.verify_json(bad,g)

    def test_import_rejects_merged_nets_changed_blackbox_and_lost_keep(self):
        g=view.graph(*self.inputs());data=self.imported(g)
        bad=deepcopy(data);m=bad['modules'][view.NAME];m['netnames']['S1']['bits']=m['netnames']['S0']['bits']
        with self.assertRaises(ValueError):view.verify_json(bad,g)
        bad=deepcopy(data);bad['modules'][view.TAIL]['attributes']['blackbox']='0'
        with self.assertRaises(ValueError):view.verify_json(bad,g)
        bad=deepcopy(data);del bad['modules'][view.NAME]['cells']['u_tail_load']['attributes']['keep']
        with self.assertRaises(ValueError):view.verify_json(bad,g)


if __name__=='__main__':unittest.main()
