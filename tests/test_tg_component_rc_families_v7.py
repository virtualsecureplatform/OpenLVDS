# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_component_rc_families_v7 as rc


class NativeComponentRestorationTests(unittest.TestCase):
    def components(self):
        result = {}
        for model, output in ((rc.circuit.previous.BUFFER, 'X'), (rc.circuit.previous.INVERTER, 'Y')):
            result[model] = (f'.subckt {model} A {output} VGND VPWR\n'
                            f'R1 A gate 1\nR2 drain {output} 2\nC1 drain VGND 3f $ **FLOATING\n'
                            'XN drain gate VGND VGND sky130_fd_pr__nfet_01v8 w=0.42 l=0.15 ad=0.1218 as=0.1218 pd=1.42 ps=1.42\n'
                            f'.ends {model}\n')
        model = rc.circuit.previous.FINE
        result[model] = (f'.subckt {model} NODE EN ENB VDD VSS\n'
                        'R1 EN ngate 1\nR2 ENB pgate 2\nR3 ENB cgate 3\nC1 pgate VSS 2f\n'
                        'XN NODE ngate cap VSS sky130_fd_pr__nfet_01v8 w=0.42 l=0.15\n'
                        'XP cap pgate NODE VDD sky130_fd_pr__pfet_01v8 w=0.84 l=0.15\n'
                        'XCLR cap cgate VSS VSS sky130_fd_pr__nfet_01v8 w=0.42 l=0.15\n'
                        'XC cap VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3\n'
                        f'.ends {model}\n')
        return result

    def ideal(self, components):
        return ''.join(rc.isolate(text, model)[0] for model, text in components.items())

    def test_exact_extracted_elements_are_restored_and_unrelated_models_retained(self):
        components = self.components()
        unrelated = '.subckt unrelated A B\nX1 A A B B sky130_fd_pr__nfet_01v8 w=1 l=.15\n.ends unrelated\n'
        text, reports = rc.restore(self.ideal(components)+unrelated, components)
        definitions = rc.native.definitions(text)
        for model, source in components.items():
            self.assertEqual(definitions[model], rc.native.definitions(source)[model])
        self.assertEqual(definitions['unrelated'], rc.native.definitions(unrelated)['unrelated'])
        self.assertTrue(all(r['native_parameters_preserved'] for r in reports))
        self.assertEqual(sum(r['restored_resistors'] for r in reports), 7)

    def test_wrong_junction_geometry_and_incomplete_component_family_are_rejected(self):
        components = self.components(); ideal = self.ideal(components)
        with self.assertRaises(ValueError):
            rc.restore(ideal.replace('ad=0.1218', 'ad=0.12', 1), components)
        altered = dict(components); altered.pop(rc.circuit.previous.FINE)
        with self.assertRaises(ValueError):
            rc.restore(ideal, altered)

    def bank(self, duplicate=False):
        model = rc.circuit.previous.FINE
        return ('.subckt bank IN OUT VPWR VGND\n'
                f'Xfine_unit0 OUT fine0 fine_b0 VPWR VGND {model}\n'
                f'Xfine_unit{0 if duplicate else 1} OUT fine1 fine_b1 VPWR VGND {model}\n.ends bank\n')

    def test_all_distributed_gate_nodes_map_to_their_correct_control_target(self):
        component = self.components()[rc.circuit.previous.FINE]
        gates = rc.fine_gate_observations(component, self.bank(), expected_units=2)
        self.assertEqual(len(gates), 6)
        self.assertIn(dict(device='XD:Xfine_unit0:XN', gate_node='XD:Xfine_unit0:ngate',
                           control_node='XD:fine0', bit=0, kind='fine'), gates)
        self.assertIn(dict(device='XD:Xfine_unit1:XCLR', gate_node='XD:Xfine_unit1:cgate',
                           control_node='XD:fine_b1', bit=1, kind='fine_b'), gates)

    def test_unknown_gates_short_controls_and_duplicate_units_are_rejected(self):
        component = self.components()[rc.circuit.previous.FINE]
        for broken in (component.replace('XN NODE ngate', 'XN NODE unknown'),
                       component.replace('C1 pgate', 'RSHORT EN ENB 1\nC1 pgate')):
            with self.assertRaises(ValueError):
                rc.fine_gate_observations(broken, self.bank(), expected_units=2)
        with self.assertRaises(ValueError):
            rc.fine_gate_observations(component, self.bank(duplicate=True), expected_units=2)


if __name__ == '__main__':
    unittest.main()
