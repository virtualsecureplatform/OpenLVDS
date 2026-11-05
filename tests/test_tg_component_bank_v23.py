# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_component_bank_v23 as circuit
import probe_tg_component_bank_v23 as pilot
import verify_tg_component_bank_v23 as proof


class ActualTGComponentTests(unittest.TestCase):
    def component(self):
        model = circuit.MODEL
        return (f'.subckt {model} A Z EN ENB VPWR VGND\n'
                'R1 EN ngate 1\nR2 ENB pgate 2\nR3 A nd 1\nC1 ngate VGND 1f\n'
                f'XN nd ngate Z VGND {circuit.proof.physical.N} w=1.68 l=.15 ad=.4872 as=.4872 pd=3.94 ps=3.94\n'
                f'XP Z pgate A VPWR {circuit.proof.physical.P} w=3.36 l=.15 ad=.9744 as=.9744 pd=7.3 ps=7.3\n'
                f'.ends {model}\n')

    def bank(self, model, profile='both3', count=20):
        name = circuit.previous.name(profile) if model == circuit.OLD else circuit.name(profile)
        return (f'.subckt {name} IN OUT VPWR VGND\n'+
                ''.join(f'Xswitch0_{i}_0 tap{i} selected en0_0 en_b0_0 VPWR VGND {model}\n' for i in range(count))+
                'Xretained IN OUT unrelated\n'+f'.ends {name}\n')

    def test_full_rc_is_installed_without_changing_unrelated_native_definitions(self):
        tg = self.component(); ideal, _ = circuit.isolate(tg, circuit.MODEL)
        cells = ideal.replace(circuit.MODEL, circuit.OLD)+'.subckt unrelated A B\nR1 A B 3\n.ends unrelated\n'
        before = circuit.previous.native.definitions(cells)
        result, bank, meta = circuit.transform(cells, self.bank(circuit.OLD), tg, 'both3')
        after = circuit.previous.native.definitions(result)
        self.assertEqual(after[circuit.MODEL], circuit.previous.native.definitions(tg)[circuit.MODEL])
        self.assertEqual(before['unrelated'], after['unrelated'])
        self.assertEqual(bank.count(' '+circuit.MODEL+'\n'), 20)
        self.assertEqual(meta['tg_component_resistors'], 3)
        self.assertFalse(meta['whole_bank_rc_retained']); self.assertFalse(meta['qualified_phy'])

    def test_actual_internal_gates_cover_all_switches_and_match_public_targets(self):
        gates = circuit.gate_observations(self.component(), self.bank(circuit.MODEL))
        self.assertEqual(len(gates), 40)
        self.assertIn(dict(device='XD:Xswitch0_0_0:XN', gate_node='XD:Xswitch0_0_0:ngate',
                           control_node='XD:en0_0', control_name='en0_0', kind='EN'), gates)
        self.assertIn(dict(device='XD:Xswitch0_19_0:XP', gate_node='XD:Xswitch0_19_0:pgate',
                           control_node='XD:en_b0_0', control_name='en_b0_0', kind='ENB'), gates)
        with self.assertRaises(ValueError):
            circuit.gate_observations(self.component(), self.bank(circuit.MODEL, count=19))
        with self.assertRaises(ValueError):
            circuit.gate_observations(self.component().replace('XN nd ngate', 'XN nd unknown'), self.bank(circuit.MODEL))

    def test_wrong_local_gate_is_rejected_even_with_safe_terminal_voltage(self):
        gates = circuit.gate_observations(self.component(), self.bank(circuit.MODEL))
        names = ['time']+['v('+g['gate_node'].replace(':', '.').lower()+')' for g in gates]
        waveform = np.tile([2e-9]+[1.8 if g['kind'] == 'EN' else 0 for g in gates], (3, 1))
        spec = dict(coarse=0, fine=0)
        self.assertTrue(all(g['passed'] for g in circuit.gate_measurements(names, waveform, gates, spec)))
        waveform[:, 1] = 1.6
        rows = circuit.gate_measurements(names, waveform, gates, spec)
        self.assertFalse(rows[0]['passed']); self.assertTrue(all(g['passed'] for g in rows[1:]))
        with self.assertRaises(ValueError):
            circuit.gate_measurements(names[1:], waveform[:, 1:], gates, spec)

    def test_zero_code_fixture_keeps_every_actual_terminal_and_public_tail(self):
        devices = [dict(terminals=['OUT', 'XD:Xswitch0_0_0:EN.t0', 'XD:Xswitch0_0_0:VGND.t0', 'VDD'])]
        with patch.dict(os.environ, PDK_ROOT='/test/pdk'):
            text = pilot.fixture(Path('/work/OpenLVDS/build/test'), pilot.specifications()[1], devices)
        for node in devices[0]['terminals']+['XD:unused_tail']:
            self.assertIn('V('+node+')', text)
        self.assertIn(' '+circuit.name('both3')+'\n', text)
        self.assertEqual(len(pilot.specifications()), 2)
        self.assertTrue(all(s['coarse'] == s['fine'] == 0 for s in pilot.specifications()))

    def test_zero_success_cannot_be_reported_as_complete_sparse_or_phy_success(self):
        rows = []
        for spec in pilot.specifications():
            result = dict(terminal_screen_passed=True, control_settling_passed=True, onehot_control_settling_passed=True,
                          repeated_delay_difference_ps=dict(rise=0, fall=0), zero_code_fast_quarter_headroom_ps=30,
                          samples=[dict(rise_delay_ps=500, fall_delay_ps=580)]*2)
            rows.append(dict(task=dict(spec=spec), result=result))
        for result in proof.comparisons(rows):
            self.assertTrue(result['zero_code_native_gate_passed'])
            self.assertFalse(result['all_sparse_points_present'])
            self.assertFalse(result['sparse_native_screen_passed'])
            self.assertFalse(result['whole_bank_rc_retained']); self.assertFalse(result['qualified_phy'])


if __name__ == '__main__':
    unittest.main()
