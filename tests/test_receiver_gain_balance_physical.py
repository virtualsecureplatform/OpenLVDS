# SPDX-License-Identifier: GPL-3.0-only
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_gain_balance as layout
import probe_receiver_gain_balance as probe


class GainBalancePhysical(unittest.TestCase):
    def test_actual_gain_pair_fingers_and_pullups_remain_local(self):
        source = (layout.ROOT/'analog/openlvds.spice').read_text()
        for variant, count, fingers in [('restore_p4_n8',74,2), ('decision_pair_w32',80,8)]:
            changed = layout.clocks.source_variant(source, True, variant)
            ports, devices = layout.physical.flatten(layout.physical.circuits(changed), layout.TOP)
            self.assertEqual(len(devices),count); self.assertEqual(len(ports),9)
            extra = [d for d in devices if '__XRBC' in d['name']]
            pair = [d for d in devices if '__XC0' in d['name'] or '__XC1' in d['name']]
            self.assertEqual(len(extra),4); self.assertEqual(len(pair),fingers)
            self.assertTrue(all(layout.geometry.critical(d) for d in extra+pair))

    def test_native_profiles_are_distinct_and_restore_on_failure(self):
        model = ' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT'])
        n = probe.native; old = n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        with self.assertRaises(RuntimeError):
            with probe.profile('decision_pair_w32',model):
                n.validate_profile(layout.profile('decision_pair_w32'))
                with self.assertRaises(ValueError):
                    n.validate_profile(layout.profile('restore_p4_n8'))
                self.assertIn('receiver_gain_balance.py',n.CODE)
                self.assertIn('receiver_restore_threshold.py',n.CODE)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),old)

    def test_old_variants_cannot_substitute_for_gain_balance_candidate(self):
        for variant in ['restore_lvt_n8','restore_lvt_n4','rail_pullup_2r']:
            with self.assertRaises(ValueError):
                layout.profile(variant)

    def test_missing_clock_controls_cannot_launch_source_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); screen=root/'matrix'; clock=root/'build/diagnostics/receiver_clamp/missing'
            clock.mkdir(parents=True)
            (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(
                gain_balance_variant='restore_p4_n8',static_screen='matrix',static_proofs={}),
                tasks=[dict(id=n) for n in layout.clocks.clock.CASES])))
            with patch.object(layout,'ROOT',root), patch.object(layout.clocks,'static_gate',return_value={}), patch.object(layout.clocks,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all three'):
                    layout.source_gate(screen,clock,'restore_p4_n8')
                run.assert_not_called()


if __name__=='__main__':
    unittest.main()
