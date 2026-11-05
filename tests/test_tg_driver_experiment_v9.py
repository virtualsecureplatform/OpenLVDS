# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_driver_experiment_v9 as circuit
import probe_tg_driver_experiment_v9 as pilot
import native_clock_components_v2 as native


class DriverSelectorExperimentTests(unittest.TestCase):
    def source(self):
        model = circuit.baseline.previous.INVERTER
        inv = f'.subckt {model} A Y VGND VPWR\nR1 A gate 2\nC1 Y VGND 4f\n'
        inv += ''.join(f'XP{i} Y gate VPWR VPWR {circuit.HVT} w=1 l=.15 ad=.135 as=.26 pd=1.27 ps=2.52\n' for i in range(8))
        inv += 'XN Y gate VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n'
        inv += f'.ends {model}\n'
        other = '.subckt unrelated A B\nR1 A B 3\n.ends unrelated\n'
        tg = circuit.baseline.previous.tg_source(circuit.baseline.PROFILE)
        top = circuit.baseline.name()
        bank = f'.subckt {top} IN OUT VPWR VGND\nXI IN OUT VGND VPWR {model}\n.ends {top}\n'
        return inv+other+tg, bank

    def test_pmos_flavor_is_the_only_inverter_change_and_all_other_rc_is_retained(self):
        cells, bank = self.source()
        result, changed_bank, report = circuit.transform(cells, bank, 'regular_double')
        expected = cells.replace(circuit.HVT, circuit.REGULAR)
        self.assertEqual(native.definitions(result), native.definitions(expected))
        self.assertEqual(changed_bank.replace(circuit.name('regular_double'), circuit.baseline.name()), bank)
        self.assertEqual(report['changed_pmos_instances'], 16)
        self.assertFalse(report['whole_bank_rc_retained'])
        self.assertFalse(report['qualified_phy'])

    def test_quad_tg_scales_junctions_once_and_preserves_hvt_control(self):
        cells, bank = self.source()
        result, _, report = circuit.transform(cells, bank, 'hvt_quad')
        before = native.definitions(cells); after = native.definitions(result)
        model = circuit.baseline.previous.tg_name(circuit.baseline.PROFILE)
        self.assertEqual({k: v for k, v in before.items() if k != model}, {k: v for k, v in after.items() if k != model})
        rows = after[model][1]
        self.assertIn('w=1.68', rows[0]); self.assertIn('w=3.36', rows[1])
        self.assertIn('ad=0.4872', rows[0]); self.assertIn('ad=0.9744', rows[1])
        self.assertEqual(report['changed_pmos_instances'], 0)

    def test_unexpected_inverter_or_tg_geometry_is_rejected(self):
        cells, bank = self.source()
        for broken in (cells.replace(circuit.HVT, circuit.REGULAR, 1), cells.replace('ad=0.2436', 'ad=0', 1)):
            with self.assertRaises(ValueError):
                circuit.transform(broken, bank, 'regular_quad')
        with self.assertRaises(ValueError):
            circuit.transform(cells, bank, 'unknown')

    def test_native_fixture_retains_all_terminals_and_explicit_passive_tail_probe(self):
        spec = pilot.specifications()[2]
        device = dict(terminals=['OUT', 'XD:Xfine_driver:A.t15', 'VDD', 'XD:Xtail_load:Y.t1'])
        with patch.dict(os.environ, PDK_ROOT='/test/pdk'):
            text = pilot.fixture(Path('/work/OpenLVDS/build/test'), spec, [device])
        for node in device['terminals']+['XD:unused_tail']:
            self.assertIn('V('+node+')', text)
        self.assertIn(' '+circuit.name(spec['profile'])+'\n', text)
        self.assertIn('/cells_regular_quad.spice"', text)
        self.assertIn('.tran 2p 20n 0 2p', text)
        self.assertEqual(len(pilot.specifications()), 18)
        self.assertEqual({(s['coarse'], s['fine']) for s in pilot.specifications()}, {(0, 0), (0, 1), (0, 15), (0, 16), (0, 31), (1, 0)})


if __name__ == '__main__':
    unittest.main()
