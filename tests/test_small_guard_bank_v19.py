# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import small_guard_bank_v19 as circuit
import probe_small_guard_bank_v19 as pilot
import verify_small_guard_bank_v19 as proof
import test_verify_tg_driver_experiment_v9 as fixtures


class ActualSmallGuardBankTests(unittest.TestCase):
    def sources(self):
        def cell(model):
            return f'.subckt {model} A Y VGND VPWR\nXN Y A VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends {model}\n'
        bank = (f'.subckt {circuit.BASE} IN OUT VPWR VGND\n'
                f'Xinput_inverse IN tap0 VGND VPWR {circuit.OLD}\n'
                f'Xfine_driver selected OUT VGND VPWR {circuit.OLD}\n'
                'Xretained OUT fine0 fine_b0 VPWR VGND unchanged_fine\n'
                f'.ends {circuit.BASE}\n')
        return cell(circuit.OLD)+'.subckt unrelated A B\nR1 A B 2\n.ends unrelated\n', bank, {n: cell(n) for n in (circuit.BIG, circuit.SMALL)}

    def test_profiles_replace_only_two_driver_models_and_retain_wiring(self):
        cells, bank, models = self.sources()
        for profile in circuit.PROFILES:
            result, changed, meta = circuit.transform(cells, bank, models, profile)
            before = circuit.native.definitions(cells); after = circuit.native.definitions(result)
            self.assertEqual(after['unrelated'], before['unrelated'])
            self.assertNotIn(circuit.OLD, after)
            self.assertIn('Xinput_inverse IN tap0 VGND VPWR '+circuit.PROFILES[profile][0], changed)
            self.assertIn('Xfine_driver selected OUT VGND VPWR '+circuit.SMALL, changed)
            self.assertIn('Xretained OUT fine0 fine_b0 VPWR VGND unchanged_fine', changed)
            self.assertTrue(meta['both_driver_rc_models_have_actual_physical_witnesses'])
            self.assertFalse(meta['whole_bank_rc_retained']); self.assertFalse(meta['qualified_phy'])

    def test_incorrect_ports_missing_driver_or_missing_component_are_rejected(self):
        cells, bank, models = self.sources()
        for altered in ({circuit.BIG: models[circuit.BIG]},
                        dict(models, **{circuit.SMALL: models[circuit.SMALL].replace('A Y VGND VPWR', 'A Y VPWR VGND')})):
            with self.assertRaises(ValueError):
                circuit.transform(cells, bank, altered, 'fine3')
        with self.assertRaises(ValueError):
            circuit.transform(cells, bank.replace('Xfine_driver', 'Xwrong'), models, 'both3')

    def test_complete_native_fixture_keeps_public_tail_and_every_actual_terminal(self):
        spec = pilot.specifications()[1]
        devices = [dict(terminals=['OUT', 'XD:Xfine_driver:A.t15', 'VDD', 'XD:Xinput_inverse:Y.t13'])]
        with patch.dict(os.environ, PDK_ROOT='/test/pdk'):
            text = pilot.fixture(Path('/work/OpenLVDS/build/test'), spec, devices)
        for node in devices[0]['terminals']+['XD:unused_tail']:
            self.assertIn('V('+node+')', text)
        self.assertIn(' '+circuit.name('both3')+'\n', text)
        self.assertIn('/cells_both3.spice"', text)
        self.assertEqual(len(pilot.specifications()), 12)

    def test_actual_component_proof_does_not_admit_whole_bank_or_phy(self):
        source = [r for r in fixtures.DiagnosticAdmissionTests().rows() if r['task']['spec']['profile'] == 'hvt_quad']
        rows = [dict(r, task=dict(r['task'], spec=dict(r['task']['spec'], profile=p))) for p in circuit.PROFILES for r in source]
        for report in proof.comparisons(rows):
            self.assertTrue(report['sparse_native_screen_passed'])
            self.assertTrue(report['inverter_rc_physically_equivalent'])
            self.assertFalse(report['whole_bank_rc_retained'])
            self.assertFalse(report['qualified_phy'])


if __name__ == '__main__':
    unittest.main()
