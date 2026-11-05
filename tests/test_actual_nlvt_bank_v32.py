# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import actual_nlvt_bank_v31 as circuit
import probe_actual_nlvt_bank_v32 as pilot
import verify_actual_nlvt_bank_v32 as proof


class ActualLowVtBankTests(unittest.TestCase):
    def test_shared_external_file_bindings_accept_only_identical_hashes(self):
        self.assertEqual(circuit.merge_files({'cad':'a'}, {'cad':'a','pdk':'b'}), {'cad':'a','pdk':'b'})
        with self.assertRaises(ValueError): circuit.merge_files({'cad':'a'}, {'cad':'changed'})

    def inputs(self):
        definitions = []; components = {}
        ports = {'tg':'A Z EN ENB VPWR VGND', 'inv3':'A Y VGND VPWR', 'bufpair':'A X VGND VPWR'}
        rows = []
        for key, old, count in [('tg',circuit.previous.TG,20), ('inv3',circuit.previous.INV,2), ('bufpair',circuit.previous.BUF,16)]:
            old += '_nlvt_diagnostic_v25'
            model = circuit.MODEL if key == 'tg' else 'actual_'+key
            definitions.append(f'.subckt {old} {ports[key]}\nR1 A Z 1\n.ends {old}\n')
            components[key] = f'.subckt {model} {ports[key]}\nR1 A Z 2\nC1 A Z 3f\n.ends {model}\n'
            rows += [f'X{key}{i} {ports[key]} {old}' for i in range(count)]
        root = circuit.previous.name('data_nlvt')
        bank = f'.subckt {root} IN OUT VPWR VGND\n'+'\n'.join(rows)+f'\n.ends {root}\n'
        return ''.join(definitions)+'.subckt keep A Z\nR1 A Z 7\n.ends keep\n', bank, components

    def test_replaces_all_data_components_and_preserves_full_rc(self):
        cells, bank, components = self.inputs()
        c, b, changes = circuit.transform(cells, bank, components)
        self.assertIn('.subckt keep A Z\nR1 A Z 7\n.ends keep', c)
        for component in components.values(): self.assertIn(component.rstrip(),c)
        self.assertEqual(b.count(' '+circuit.MODEL+'\n'),20)
        self.assertEqual(changes['actual_component_counts'],dict(tg=20,inv3=2,bufpair=16))
        self.assertFalse(changes['borrowed_changed_implant_rc'])
        self.assertFalse(changes['whole_bank_rc_retained']); self.assertFalse(changes['qualified_phy'])

    def test_missing_instance_or_changed_public_port_order_is_rejected(self):
        cells, bank, components = self.inputs()
        with self.assertRaises(ValueError): circuit.transform(cells,bank.replace('Xtg0 ', '*Xtg0 ',1),components)
        # Remove the instance, rather than commenting it: the structural parser
        # validates count independently of electrical equivalence.
        missing = '\n'.join(line for line in bank.splitlines() if not line.startswith('Xtg0 '))+'\n'
        with self.assertRaises(ValueError): circuit.transform(cells, missing, components)
        changed = dict(components, inv3=components['inv3'].replace('A Y VGND VPWR','A Y VPWR VGND'))
        with self.assertRaises(ValueError): circuit.transform(cells,bank,changed)

    def test_matched_fixture_uses_new_libraries_and_root(self):
        with patch.dict(os.environ,PDK_ROOT='/test/pdk'):
            text = pilot.fixture(Path('/work/OpenLVDS/build/example'),pilot.specifications()[0],[])
        self.assertIn(' '+circuit.name('actual_nlvt')+'\n',text)
        self.assertIn('cells_actual_nlvt.spice',text)
        self.assertNotIn('cells_data_nlvt.spice',text)
        self.assertEqual(len(pilot.specifications()),1)

    def test_zero_pass_never_admits_sparse_or_phy(self):
        spec = pilot.specifications()[0]
        result = dict(terminal_screen_passed=True,control_settling_passed=True,onehot_control_settling_passed=True,
                      repeated_delay_difference_ps=dict(rise=0,fall=0),zero_code_fast_quarter_headroom_ps=20,
                      samples=[dict(rise_delay_ps=500,fall_delay_ps=580)]*2)
        report = proof.comparisons([dict(task=dict(spec=spec),result=result)])[0]
        self.assertTrue(report['zero_code_native_gate_passed'])
        self.assertFalse(report['all_sparse_points_present']); self.assertFalse(report['qualified_phy'])


if __name__ == '__main__': unittest.main()
