# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_matched_trip as physical
import layout_receiver_differential_restore as previous
import probe_receiver_matched_trip as probe


class MatchedTripPhysical(unittest.TestCase):
    def test_old_trip_family_cannot_select_new_physical_profile(self):
        for variant in physical.clocks.VARIANTS:
            selected=physical.profile(variant)
            self.assertEqual(selected['matched_trip_variant'],variant)
            self.assertNotIn('differential_restore_variant',selected)
            self.assertNotEqual(selected['routing'],previous.profile('track_t8_r7')['routing'])
        for old in ['control','track_t8_r7','track_t16_r7','decision_pair_w32']:
            with self.assertRaises(ValueError):physical.profile(old)

    def test_other_source_clock_family_cannot_trigger_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);matrix=root/'build/diagnostics/receiver_matched_trip_matrix/test'
            clock=root/'build/diagnostics/receiver_clamp/old';clock.mkdir(parents=True)
            (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(
                differential_restore_variant='track_t16_r7',static_screen=str(matrix.relative_to(root))),tasks=[])))
            with patch.object(physical,'ROOT',root), patch.object(physical.clocks,'static_gate',return_value={}), patch.object(physical.clocks,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all three'):
                    physical.source_gate(matrix,clock,'matched_t16_r7')
                run.assert_not_called()

    def test_native_profile_and_observation_restore_after_failure(self):
        model=' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT','AMP_CT','AMP_L','AMP_OUT','CO_TRACK'])
        n=probe.native;before=n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        with self.assertRaises(RuntimeError):
            with probe.profile('matched_t8_r7',model) as nodes:
                n.validate_profile(physical.profile('matched_t8_r7'))
                with self.assertRaises(ValueError):n.validate_profile(previous.profile('track_t8_r7'))
                self.assertEqual(len(nodes),10)
                self.assertIn('receiver_matched_trip_restore.py',n.CODE)
                self.assertIn('receiver_matched_trip_clock.py',n.CODE)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),before)
