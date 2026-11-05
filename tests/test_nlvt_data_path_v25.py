# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import nlvt_data_path_v25 as circuit
import probe_nlvt_data_path_v25 as pilot
import verify_nlvt_data_path_v25 as proof


class LegalNMOSFlavorIsolationTests(unittest.TestCase):
    def source(self):
        def cell(model, pmodel):
            return (f'.subckt {model} A Y VGND VPWR\nR1 A gate 2\nC1 Y VGND 3f\n'
                    f'XN Y gate VGND VGND {circuit.N} w=.65 l=.15 ad=.08775 as=.169 pd=.92 ps=1.82\n'
                    f'XP Y gate VPWR VPWR {pmodel} w=1 l=.15 ad=.135 as=.26 pd=1.27 ps=2.52\n.ends {model}\n')
        cells = cell(circuit.TG, circuit.P)+cell(circuit.INV, circuit.P)+cell(circuit.BUF, circuit.PHVT)+cell('untouched_fine_control', circuit.P)
        root = circuit.baseline.name('both3')
        body = ''.join(f'Xswitch{i} A Z EN ENB VPWR VGND {circuit.TG}\n' for i in range(20))
        body += ''.join(f'Xdriver{i} IN OUT VGND VPWR {circuit.INV}\n' for i in range(2))
        body += ''.join(f'Xbuffer{i} IN OUT VGND VPWR {circuit.BUF}\n' for i in range(16))
        return cells, f'.subckt {root} IN OUT VPWR VGND\n'+body+f'.ends {root}\n'

    def test_tg_only_changes_preserve_all_unselected_components_and_rc(self):
        cells, bank = self.source(); result, changed, meta = circuit.transform(cells, bank, 'tg_nlvt')
        before = circuit.baseline.previous.native.definitions(cells); after = circuit.baseline.previous.native.definitions(result)
        for model in (circuit.INV, circuit.BUF, 'untouched_fine_control'):
            self.assertEqual(before[model], after[model])
        self.assertEqual(meta['native_nmos_model_changes'], 20)
        self.assertEqual(meta['native_pmos_model_changes'], 0)
        self.assertEqual(result.count('R1 A gate 2'), cells.count('R1 A gate 2'))
        self.assertIn('l=.15 ad=.08775 as=.169 pd=.92 ps=1.82', result)
        self.assertNotIn('sky130_fd_pr__pfet_01v8_lvt', result)
        self.assertFalse(meta['new_implant_physical_proof']); self.assertFalse(meta['qualified_phy'])

    def test_data_path_flavors_retain_controls_junctions_and_all_passive_values(self):
        cells, bank = self.source(); result, _, meta = circuit.transform(cells, bank, 'data_nlvt')
        self.assertEqual(meta['native_nmos_model_changes'], 38)
        self.assertEqual(meta['native_pmos_model_changes'], 16)
        before = circuit.baseline.previous.native.definitions(cells)
        after = circuit.baseline.previous.native.definitions(result)
        self.assertEqual(before['untouched_fine_control'], after['untouched_fine_control'])
        for change in meta['changed_components']:
            old = before[change['original_model']][1]; new = after[change['diagnostic_model']][1]
            expected = [[v.replace(circuit.N, circuit.NLVT).replace(circuit.PHVT, circuit.P) for v in row] for row in old]
            self.assertEqual(new, expected)
        self.assertEqual(len(pilot.specifications()), 2)
        self.assertTrue(all(s['coarse'] == s['fine'] == 0 for s in pilot.specifications()))

    def test_illegal_lvt_geometry_and_changed_instance_counts_are_rejected(self):
        cells, bank = self.source()
        for broken in (cells.replace('w=.65', 'w=.41', 1), cells.replace('l=.15', 'l=.14', 1)):
            with self.assertRaises(ValueError):
                circuit.transform(broken, bank, 'tg_nlvt')
        with self.assertRaises(ValueError):
            circuit.transform(cells, bank.replace('Xswitch0 A Z EN ENB VPWR VGND '+circuit.TG+'\n', ''), 'tg_nlvt')


if __name__ == '__main__':
    unittest.main()
