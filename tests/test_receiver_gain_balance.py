# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_gain_balance as experiment
import matrix_receiver_gain_balance as matrix
from layout import circuits,flatten


class ReceiverGainBalance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=experiment.baseline.source_variant((experiment.ROOT/'analog/openlvds.spice').read_text(),True)

    def test_control_is_exact_source_qualified_p8_n8_lvt_receiver(self):
        self.assertEqual(experiment.transform(self.source,'control'),
                         experiment.control.transform(self.source,'restore_lvt_n8'))

    def test_balance_intervention_changes_only_first_pmos_width(self):
        before=circuits(experiment.transform(self.source,'control'))
        after=circuits(experiment.transform(self.source,'restore_p4_n8'))
        self.assertEqual(set(before),set(after))
        expected=deepcopy(before)
        ports,rows=expected[experiment.HELPER]
        rows[0][3]['w']='4'
        self.assertEqual(after,expected)
        self.assertEqual(after[experiment.HELPER][1][1][3]['w'],'8')

    def test_gain_intervention_changes_only_pair_widths_and_keeps_bias_ratios(self):
        before=circuits(experiment.transform(self.source,'control'))
        after=circuits(experiment.transform(self.source,'decision_pair_w32'))
        expected=deepcopy(before)
        for row in expected[experiment.TOP][1]:
            if row[0] in ['XC0','XC1']:row[3]['w']='32'
        self.assertEqual(after,expected)
        old_ports,old=flatten(before,experiment.TOP);new_ports,new=flatten(after,experiment.TOP)
        self.assertEqual(old_ports,new_ports)
        self.assertEqual(len(old),74);self.assertEqual(len(new),80)

    def test_already_modified_and_unknown_inputs_are_rejected(self):
        with self.assertRaises(ValueError):experiment.transform(self.source,'unknown')
        for variant in experiment.VARIANTS:
            with self.assertRaises(ValueError):
                experiment.transform(experiment.transform(self.source,variant),variant)

    def test_observer_measures_actual_new_dimensions_and_all_twelve_devices(self):
        for variant in experiment.VARIANTS:
            devices=experiment.observed_devices(experiment.instrument(experiment.transform(self.source,variant)))
            self.assertEqual(len(devices),12)
            self.assertEqual(devices['XC0'][3]['w'],'32' if variant=='decision_pair_w32' else '8')
            self.assertEqual(devices['XIB0/XP'][3]['w'],'4' if variant=='restore_p4_n8' else '8')
            self.assertEqual(devices['XIB0/XN'][2],'sky130_fd_pr__nfet_01v8_lvt')

    def test_failure_corners_and_each_variant_gate_are_independent(self):
        self.assertEqual(matrix.PILOTS[:2],[('ss',40),('fs',40)])
        self.assertEqual(len(set(matrix.PILOTS)),6)
        reports=[dict(results=[dict(task=v,passed=True,metrics=dict(metrics=dict(passed=True)),
            twelve_device_observations=dict(observed_thin_guard_passed=True)) for v in experiment.VARIANTS]) for _ in range(15)]
        reports[0]['results'][1]['passed']=False
        gate=matrix.admission(reports)
        self.assertFalse(gate['restore_p4_n8']['source_dc_passed'])
        self.assertTrue(gate['decision_pair_w32']['source_dc_passed'])
        self.assertFalse(matrix.admission(reports[:6])['decision_pair_w32']['source_dc_passed'])


if __name__=='__main__':
    unittest.main()
