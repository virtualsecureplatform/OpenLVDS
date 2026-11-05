# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import uniform_tree_netlist_v3 as view
import export_uniform_tree_netlist_v3 as export

ROOT = Path(__file__).resolve().parents[1]


def orders():
    sc = view.native.SC
    return {
        view.native.BUFFER: ['A', 'X', 'VGND', 'VPWR'],
        view.native.fine.NAME: ['NODE', 'EN', 'ENB', 'VDD', 'VSS'],
        **{sc+model: ['A', 'VGND', 'VNB', 'VPB', 'VPWR', output]
           for model, output in [('buf_1', 'X'), ('buf_4', 'X'), ('inv_1', 'Y')]},
        sc+'mux4_4': ['A0', 'A1', 'A2', 'A3', 'S0', 'S1', 'VGND', 'VNB', 'VPB', 'VPWR', 'X'],
        sc+'mux2_4': ['A0', 'A1', 'S', 'VGND', 'VNB', 'VPB', 'VPWR', 'X'],
    }


class UniformPhysicalViewTests(unittest.TestCase):
    def test_all_declared_dimensions_compile_with_explicit_native_interfaces(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for coarse in (16, 32, 64, 128, 256):
                for fine in (16, 32):
                    with self.subTest(coarse=coarse, fine=fine):
                        (folder/'bank.v').write_text(view.verilog(orders(), coarse, fine))
                        (folder/'cells.v').write_text(view.blackboxes(orders(), coarse, fine))
                        p = subprocess.run(['iverilog', '-g2012', '-Wall', '-s', view.name(coarse, fine),
                                            '-t', 'null', str(folder/'cells.v'), str(folder/'bank.v')], capture_output=True, text=True)
                        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
                        self.assertFalse(p.stderr, p.stderr)

    def test_checked_in_default_matches_native_component_port_orders(self):
        self.assertEqual((ROOT/'sky130/v2'/f'{view.name()}.v').read_text(), view.verilog(orders()))
        self.assertEqual((ROOT/'sky130/v2/uniform_tree_physical_blackboxes_v3.v').read_text(), view.blackboxes(orders()))

    def test_native_spice_graph_is_preserved_and_component_corruption_rejected(self):
        cells = '\n'.join('.subckt '+model+' '+' '.join(pins)+'\n.ends '+model for model, pins in orders().items())+'\n'
        bank = view.native.source(orders())
        _, graph = export.native_graph(bank, cells)
        self.assertEqual(len(graph), 120)
        self.assertEqual(next(c for c in graph if c['name'] == 'u_tail_load')['pins']['A'], 'tap15')
        for broken in (bank.replace('Xtail_load ', '*Xtail_load ', 1),
                       bank.replace('Xfine_unit15 ', '*Xfine_unit15 ', 1),
                       bank.replace('Xdelay1 tap0 ', 'Xdelay1 tap1 ', 1)):
            with self.assertRaises(ValueError):
                export.native_graph(broken, cells)

    def test_missing_native_body_or_supply_ports_are_rejected(self):
        for model, pin in ((view.native.SC+'mux4_4', 'VPB'),
                           (view.native.BUFFER, 'VGND'), (view.native.fine.NAME, 'VSS')):
            altered = orders(); altered[model] = [p for p in altered[model] if p != pin]
            with self.assertRaises(ValueError):
                view.verilog(altered)


if __name__ == '__main__':
    unittest.main()
