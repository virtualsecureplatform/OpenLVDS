# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_tia_restore as factory
import screen_receiver_tia_restore as screen
from layout import circuits,flatten


class FeedbackInverterReceiver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()

    def test_control_is_exact_qualified_n8_source(self):
        self.assertEqual(factory.source_variant(self.source,'control'),factory.baseline.source_variant(self.source,'control'))

    def test_feedback_uses_only_original_series_poly_units_from_output_to_input(self):
        for variant,count in [('tia_r2',2),('tia_r4',4)]:
            source=factory.source_variant(self.source,variant);rows={r[0]:r for r in circuits(source)[factory.TOP][1]}
            self.assertEqual(rows['XIB0'][1:3],(['CO','RESTORE0','VDDD','VSS'],'lvds_inv18_drive'))
            chain=['CO']+['FB'+str(i) for i in range(1,count)]+['RESTORE0']
            for i in range(count):self.assertEqual(rows['XRFB'+str(i)][1:],([chain[i],chain[i+1],'VSS'],factory.RES,dict(w='0.35',l='1.25')))
            self.assertEqual(len([n for n in rows if n.startswith('XRFB')]),count)
            self.assertFalse(any(n in rows for n in ['XAT','XA0','XA1','XAD','XAM']))

    def test_original_frontend_pair_bias_reference_and_later_buffers_are_preserved(self):
        old=circuits(factory.source_variant(self.source,'control'));rows={r[0]:r for r in old[factory.TOP][1]}
        for variant in factory.VARIANTS[1:]:
            new=circuits(factory.source_variant(self.source,variant));after={r[0]:r for r in new[factory.TOP][1]}
            self.assertEqual(set(old),set(new))
            for name,value in old.items():
                if name!=factory.TOP:self.assertEqual(value,new[name])
            for name,value in rows.items():
                if name!='XIB0':self.assertEqual(value,after[name])

    def test_real_flattened_counts_ports_and_observed_devices(self):
        for variant,count in [('control',74),('tia_r2',77),('tia_r4',79)]:
            source=factory.source_variant(self.source,variant);ports,devices=flatten(circuits(source),factory.TOP)
            self.assertEqual(len(ports),9);self.assertEqual(len(devices),count)
            observed=screen.observed_devices(screen.instrument(source))
            self.assertEqual(len(observed),14)
            if variant!='control':self.assertEqual(observed['XIB0/XP'][3]['w'],'16')

    def test_modified_and_unknown_parents_are_refused(self):
        with self.assertRaises(ValueError):factory.source_variant(self.source,'tia_r8')
        with self.assertRaises(ValueError):factory.transform(factory.source_variant(self.source,'tia_r2'),'tia_r4')
