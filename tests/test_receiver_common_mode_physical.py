# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_common_mode as physical
import probe_receiver_common_mode as probe


class CommonModePhysical(unittest.TestCase):
    def test_corrected_resistors_remain_in_local_frontend_cluster(self):
        source = (physical.ROOT/'analog/openlvds.spice').read_text()
        for variant, expected_count in [('reference_return', 70), ('rail_pullup', 72)]:
            changed = physical.clocks.source_variant(source, True, variant)
            ports, devices = physical.physical.flatten(physical.physical.circuits(changed), physical.TOP)
            self.assertEqual(len(ports), 9)
            self.assertEqual(len(devices), expected_count)
            changed_names = ['XRLPPE', 'XRLPNE'] if variant == 'reference_return' else ['XRBCPP', 'XRBCPN']
            for name in changed_names:
                selected = [d for d in devices if d['name'].endswith('__'+name)]
                self.assertEqual(len(selected), 1)
                self.assertTrue(physical.geometry.critical(selected[0]))
            self.assertCountEqual(physical.geometry.ordered(devices), devices)

    def test_clock_from_other_correction_cannot_admit_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); clock = root/'build/diagnostics/receiver_clamp/wrong'; clock.mkdir(parents=True)
            (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(passive_common_mode_variant='rail_pullup'), tasks=[])))
            with patch.object(physical, 'ROOT', root), patch.object(physical.clocks, 'static_gate', return_value={}), patch.object(physical.clocks, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'exact correction'):
                    physical.source_gate(root/'matrix', clock, 'reference_return')
                run.assert_not_called()

    def test_missing_geometry_cannot_create_native_context(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(probe.native, 'prepare') as prepare:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'geometry and RC audit'):
                probe.prepare(root/'parent', root, root/'matrix', root/'clock', 'reference_return')
            prepare.assert_not_called()

    def test_native_profile_keeps_numerics_and_restores_every_binding(self):
        n = probe.native
        old = n.PROFILE, n.CODE, n.source_gate, n.source_variant, n.replay_deck, n.lease
        model = ' '.join('openlvds_receiver_core__'+leaf for leaf in ['NL', 'NR', 'PL', 'PR', 'NT', 'PT'])
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with probe.profile('rail_pullup', model):
                n.validate_profile(physical.profile('rail_pullup'))
                with self.assertRaises(ValueError):
                    n.validate_profile(physical.profile('reference_return'))
                deck = 'Replay\n.tran 5p 80n 0 1p\n.print tran V(RCP)\n.end\n'
                changed = n.replay_deck(deck, 1)
                self.assertEqual(n.replay_deck(changed, 1), changed)
                with self.assertRaises(ValueError):
                    n.replay_deck(deck, 2)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE, n.CODE, n.source_gate, n.source_variant, n.replay_deck, n.lease), old)


if __name__ == '__main__':
    unittest.main()
