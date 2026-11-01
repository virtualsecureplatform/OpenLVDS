# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_restore_threshold as experiment
import matrix_receiver_restore_threshold as matrix
from layout import circuits, flatten


class ReceiverRestoreThreshold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = experiment.baseline.source_variant(
            (experiment.ROOT/'analog/openlvds.spice').read_text(), True)

    def test_control_is_exact_qualified_two_unit_frontend(self):
        self.assertEqual(experiment.transform(self.source, 'control'),
                         experiment.bias.transform(self.source, 'rail_pullup_2r'))

    def test_only_first_restorer_model_and_selected_width_change(self):
        control = circuits(experiment.transform(self.source, 'control'))
        for variant, width in [('restore_lvt_n4', '4'), ('restore_lvt_n8', '8')]:
            candidate = circuits(experiment.transform(self.source, variant))
            self.assertEqual(set(candidate), set(control) | {experiment.HELPER})
            for name, definition in control.items():
                if name != experiment.TOP:
                    self.assertEqual(candidate[name], definition)
            ports, rows = deepcopy(control[experiment.TOP])
            rows = [(n, pins, experiment.HELPER if n == 'XIB0' else model, params)
                    for n, pins, model, params in rows]
            self.assertEqual(candidate[experiment.TOP], (ports, rows))
            helper_ports, helper = candidate[experiment.HELPER]
            self.assertEqual(helper_ports, ['A', 'Y', 'VDD', 'VSS'])
            self.assertEqual(helper, [
                ('XP', ['Y', 'A', 'VDD', 'VDD'], 'sky130_fd_pr__pfet_01v8', dict(w='8', l='0.15')),
                ('XN', ['Y', 'A', 'VSS', 'VSS'], 'sky130_fd_pr__nfet_01v8_lvt', dict(w=width, l='0.15'))])

    def test_n4_flattening_changes_exactly_one_transistor_model(self):
        _, before = flatten(circuits(experiment.transform(self.source, 'control')), experiment.TOP)
        _, after = flatten(circuits(experiment.transform(self.source, 'restore_lvt_n4')), experiment.TOP)
        self.assertEqual(len(before), len(after))
        changes = [(a,b) for a,b in zip(before, after) if a != b]
        self.assertEqual(len(changes), 1)
        a,b = changes[0]
        self.assertTrue(a['name'].endswith('__XIB0__XN_F0'))
        self.assertEqual(dict(a, model='sky130_fd_pr__nfet_01v8_lvt'), b)

    def test_unknown_or_already_modified_source_is_rejected(self):
        with self.assertRaises(ValueError):
            experiment.transform(self.source, 'unknown')
        for variant in experiment.VARIANTS:
            with self.assertRaises(ValueError):
                experiment.transform(experiment.transform(self.source, variant), variant)

    def test_pilot_corners_and_variant_specific_stress_gate(self):
        self.assertEqual(len(matrix.PILOTS), 6)
        self.assertEqual(len(set(matrix.PILOTS)), 6)
        for corner in [('ss',40), ('sf',0), ('fs',0), ('tt',25), ('sf',25), ('fs',40)]:
            self.assertIn(corner, matrix.PILOTS)
        reports = [dict(results=[dict(task=v, passed=True, metrics=dict(metrics=dict(passed=True)),
            twelve_device_observations=dict(observed_thin_guard_passed=True))
            for v in experiment.VARIANTS]) for _ in range(15)]
        reports[0]['results'][1]['twelve_device_observations']['observed_thin_guard_passed'] = False
        gates = matrix.admission(reports)
        self.assertFalse(gates['restore_lvt_n4']['source_dc_passed'])
        self.assertTrue(gates['restore_lvt_n8']['source_dc_passed'])
        self.assertFalse(matrix.admission(reports[:6])['restore_lvt_n8']['source_dc_passed'])
        self.assertTrue(matrix.admission(reports[:6], required=6)['restore_lvt_n8']['source_dc_passed'])


if __name__ == '__main__':
    unittest.main()
