# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_frontend_geometry as geometry
import probe_receiver_frontend as probe


class FrontendLocalReceiver(unittest.TestCase):
    def test_input_mirrors_tails_and_load_midpoints_stay_local(self):
        for leaf in ['NL', 'NR', 'PL', 'PR', 'NT', 'PT', 'PP', 'PN', 'PPRT', 'PNRB']:
            self.assertTrue(geometry.critical(dict(name='openlvds_receiver_core__X', nodes=['openlvds_receiver_core__'+leaf])))
        self.assertFalse(geometry.critical(dict(name='openlvds_receiver_core__XTRACK__XP', nodes=['openlvds_receiver_core__CO_TRACK', 'VDDD'])))

    def test_ordering_preserves_every_device_and_its_parameters(self):
        devices = [dict(name='openlvds_receiver_core__X'+str(i), nodes=[n], model='test', params={'w': i})
            for i, n in enumerate(['VDDD', 'openlvds_receiver_core__NL', 'openlvds_receiver_core__PPRB', 'VSS'])]
        self.assertCountEqual(geometry.ordered(devices), devices)

    def test_extra_native_probes_are_idempotent_and_do_not_change_timing(self):
        deck = 'Replay\n.tran 5p 80n 0 1p\n.print tran V(RCP)\n.end\n'
        changed = probe.add_probes(deck, ['XRC:openlvds_receiver_core__NL'])
        self.assertEqual(probe.add_probes(changed, ['XRC:openlvds_receiver_core__NL']), changed)
        self.assertEqual(changed.replace(' V(XRC:openlvds_receiver_core__NL)', ''), deck)

    def test_native_profile_and_resource_binding_restore_after_failure(self):
        model = ' '.join('openlvds_receiver_core__'+n for n in ['NL', 'NR', 'PL', 'PR', 'NT', 'PT'])
        n = probe.native; previous = n.PROFILE, n.CODE, n.replay_deck, n.lease
        with self.assertRaises(RuntimeError):
            with probe.profile(model):
                n.validate_profile(probe.PROFILE)
                with self.assertRaises(ValueError):
                    n.validate_profile(previous[0])
                raise RuntimeError('test failure')
        self.assertEqual(previous, (n.PROFILE, n.CODE, n.replay_deck, n.lease))


if __name__ == '__main__':
    unittest.main()
