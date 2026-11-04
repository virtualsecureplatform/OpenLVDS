# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_weighted_direct_v3 as circuit
import probe_weighted_direct_v3 as pilot
import weighted_bank_control_gate_v2 as gate


class PhysicalComponentBankTests(unittest.TestCase):
    def test_all_coarse_choices_and_pair_connections_are_retained(self):
        original=circuit.previous.core_instances('plain')
        actual=circuit.core_instances('guarded')
        self.assertEqual(len(actual),len(original))
        paired=circuit.direct.COMPOUNDS[circuit.direct.native.SC+'nand2b_4']
        for old,new in zip(original,actual):
            self.assertEqual(old['name'],new['name'])
            self.assertEqual(old['pins'],new['pins'])
            self.assertEqual(new['model'],circuit.GUARD if old['model']==paired else old['model'])
        self.assertEqual(sum(c['model']==circuit.GUARD for c in actual),31)
        self.assertEqual(len([c for c in actual if c['name'].startswith('turn')]),16)
        self.assertEqual(len([c for c in actual if c['name'].startswith('pass')]),15)
        self.assertFalse(any(c['name'] in ['input_buffer','output_buffer'] for c in actual))

    def test_native_fine_and_control_models_replace_every_source_fine_cell(self):
        orders={c['model']:list(c['pins']) for c in circuit.core_instances('guarded')}
        orders[circuit.controls.native.CLOCK_BUFFER]=['VGND','X','VPWR','A']
        orders[circuit.controls.native.MODELS['inv_8']]=['A','VGND','Y','VPWR']
        for b in range(5):orders[circuit.controls.unit.name(b)]=['VSS','NODE','VDD','ENB','EN']
        text=circuit.source('guarded',orders)
        self.assertNotIn('weighted_root_',text)
        self.assertNotIn('sky130_fd_sc_hd__buf_1',text)
        for b in range(5):
            self.assertIn(f'Xfine{b} VSS OUT VDD fine_b{b} fine{b} '+circuit.controls.unit.name(b),text)
            self.assertIn(f'Xfine_buffer{b} VSS fine{b} VDD B{b} '+circuit.controls.native.CLOCK_BUFFER,text)
        del orders[circuit.controls.unit.name(4)]
        with self.assertRaises(ValueError):circuit.source('guarded',orders)

    def test_native_device_walk_preserves_internal_terminal_names(self):
        text=f'''.subckt {circuit.NAME} {' '.join(circuit.PORTS)}
X0 internal OUT IN VSS {circuit.weighted.N} w=.42 l=.15
R0 internal OUT 2
C0 internal VSS 3f
.ends {circuit.NAME}
'''
        devices=circuit.devices(text)
        self.assertEqual(devices[0]['terminals'],['XD:internal','OUT','IN','0'])
        self.assertEqual(devices[0]['limit_v'],1.95)
        with self.assertRaises(ValueError):circuit.devices(text+text)

    def test_full_bank_requires_guarded_control_safety_at_both_data_biases(self):
        guarded=dict(mode='guarded',data_bias_cases=2,component_pilot_passed=True,
                     control_settling_passed=True,terminal_screen_passed=True,
                     maximum_terminal_difference_v=1.9)
        source=dict(guarded,mode='source',component_pilot_passed=False,
                    terminal_screen_passed=False,maximum_terminal_difference_v=2.08)
        self.assertTrue(gate.eligible([guarded,source]))
        for change in [dict(data_bias_cases=1),dict(component_pilot_passed=False),
                       dict(control_settling_passed=False),dict(terminal_screen_passed=False),
                       dict(maximum_terminal_difference_v=1.951),dict(maximum_terminal_difference_v=-1),
                       dict(maximum_terminal_difference_v=float('nan'))]:
            row=deepcopy(guarded);row.update(change)
            self.assertFalse(gate.eligible([row,source]))
        self.assertFalse(gate.eligible([guarded,guarded]))
        self.assertFalse(gate.eligible([source]))

    def test_both_adjacent_coarse_settings_keep_lsb_carry_and_repeat_coverage(self):
        specs=pilot.specifications()
        self.assertEqual([s['coarse'] for s in specs],[0,1])
        for s in specs:
            self.assertEqual(s['codes'],[0,1,15,16,31,0])
            self.assertEqual((s['process'],s['temperature']),('ss',40))
