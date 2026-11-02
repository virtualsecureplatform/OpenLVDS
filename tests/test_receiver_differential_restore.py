# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_differential_restore as circuit
from layout import circuits,flatten


class DifferentialRestoration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()
        cls.control=circuit.source_variant(cls.canonical,'control')

    def test_control_is_exact_source_qualified_n8_with_original_input_pair(self):
        self.assertEqual(self.control,circuit.baseline.transform(circuit.original.source_variant(self.canonical,True),'control'))
        rows={r[0]:r for r in circuits(self.control)[circuit.TOP][1]}
        self.assertEqual(rows['XC0'][3]['w'],'8');self.assertEqual(rows['XC1'][3]['w'],'8')

    def test_frontend_first_decision_bias_and_later_helpers_are_unchanged(self):
        before=circuits(self.control);old={r[0]:r for r in before[circuit.TOP][1]}
        for variant in circuit.VARIANTS[1:]:
            after=circuits(circuit.source_variant(self.canonical,variant));new={r[0]:r for r in after[circuit.TOP][1]}
            self.assertEqual(set(before),set(after))
            for name,definition in before.items():
                if name!=circuit.TOP:self.assertEqual(definition,after[name])
            for name,row in old.items():
                if name!='XIB0':self.assertEqual(row,new[name])
            self.assertEqual(set(new)-set(old),set(circuit.AMPLIFIER)|{f'XRFB{i}' for i in range(7)})

    def test_feedback_is_seven_real_original_poly_units_to_trip_replica(self):
        definitions=circuits(circuit.source_variant(self.canonical,'track_t16_r7'))
        rows={r[0]:r for r in definitions[circuit.TOP][1]}
        feedback=[r for n,r in rows.items() if n.startswith('XRFB')]
        self.assertEqual(len(feedback),7)
        self.assertTrue(all(r[1]==['AMP_OUT','CO_TRACK','VSS'] and r[2]==circuit.RES and r[3]==dict(w='0.35',l='1.25') for r in feedback))
        self.assertEqual(rows['XTRACK'][1],['CO_TRACK','CO_TRACK','VDDD','VSS'])

    def test_new_first_inverter_matches_trip_replica_models_and_ratio(self):
        d=circuits(circuit.source_variant(self.canonical,'track_t8_r7'));r={r[0]:r for r in d[circuit.TOP][1]}
        self.assertEqual(r['XIB0'][1],['AMP_OUT','RESTORE0','VDDD','VSS'])
        self.assertEqual(r['XIB0'][2],r['XIB1'][2])
        first={r[0]:r for r in d[r['XIB0'][2]][1]};track={r[0]:r for r in d[r['XTRACK'][2]][1]}
        for name in ['XP','XN']:
            self.assertEqual(first[name][2],track[name][2])
            self.assertEqual(float(track[name][3]['w']),2*float(first[name][3]['w']))

    def test_amplifier_orientation_and_scaled_controls_are_explicit(self):
        for variant,scale in [('track_t8_r7',1),('track_t16_r7',2)]:
            d=circuits(circuit.source_variant(self.canonical,variant));r={r[0]:r for r in d[circuit.TOP][1]}
            self.assertEqual(r['XA0'][1],['AMP_L','CO','AMP_CT','VSS'])
            self.assertEqual(r['XA1'][1],['AMP_OUT','CL','AMP_CT','VSS'])
            self.assertEqual(r['XAT'][1],['AMP_CT','NBC','VSS','VSS'])
            for n,width in [('XAT',8),('XA0',8),('XA1',8),('XAD',4),('XAM',4)]:
                self.assertEqual(float(r[n][3]['w']),width*scale)

    def test_real_flattened_device_counts_and_public_ports(self):
        for variant,count in [('control',74),('track_t8_r7',87),('track_t16_r7',90)]:
            ports,devices=flatten(circuits(circuit.source_variant(self.canonical,variant)),circuit.TOP)
            self.assertEqual(len(ports),9);self.assertEqual(len(devices),count)

    def test_modified_or_wrong_parent_cannot_be_transformed_again(self):
        for variant in circuit.VARIANTS[1:]:
            changed=circuit.source_variant(self.canonical,variant)
            with self.assertRaises(ValueError):circuit.transform(changed,variant)
        changed=circuit.baseline.transform(circuit.original.source_variant(self.canonical,True),'decision_pair_w32')
        with self.assertRaises(ValueError):circuit.transform(changed,'track_t8_r7')
        with self.assertRaises(ValueError):circuit.source_variant(self.canonical,'unknown')


if __name__=='__main__':
    unittest.main()
