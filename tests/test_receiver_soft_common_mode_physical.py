# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_soft_common_mode as layout
import probe_receiver_soft_common_mode as probe


class SoftCommonModePhysical(unittest.TestCase):
    def test_all_actual_added_segments_stay_local_without_changing_devices(self):
        source = (layout.ROOT/'analog/openlvds.spice').read_text()
        for variant, count in [('rail_pullup_2r',74), ('rail_pullup_3r',76)]:
            changed = layout.clocks.source_variant(source, True, variant)
            ports, devices = layout.physical.flatten(layout.physical.circuits(changed), layout.TOP)
            self.assertEqual(len(devices),count); self.assertEqual(len(ports),9)
            extra = [d for d in devices if '__XRBC' in d['name']]
            self.assertEqual(len(extra), count-70)
            self.assertTrue(all(layout.geometry.critical(d) for d in extra))
            old = layout.geometry.original.critical
            with patch.object(layout.geometry.original, 'draw_macro', return_value='drawn') as draw:
                self.assertEqual(layout.geometry.draw_macro(None,layout.TOP,ports,devices,None), 'drawn')
                draw.assert_called_once_with(None,layout.TOP,ports,devices,None)
            self.assertIs(layout.geometry.original.critical, old)

    def test_geometry_bindings_restore_on_draw_failure(self):
        old = layout.geometry.original.critical
        with patch.object(layout.geometry.original, 'draw_macro', side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError,'injected'):
                layout.geometry.draw_macro(None,layout.TOP,[],[],None)
        self.assertIs(layout.geometry.original.critical, old)

    def test_distinct_native_profiles_and_restoration(self):
        model = ' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT'])
        n = probe.native; old = n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        with self.assertRaises(RuntimeError):
            with probe.profile('rail_pullup_3r',model):
                n.validate_profile(layout.profile('rail_pullup_3r'))
                with self.assertRaises(ValueError):
                    n.validate_profile(layout.profile('rail_pullup_2r'))
                self.assertIn('receiver_soft_frontend_geometry.py',n.CODE)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),old)


if __name__ == '__main__':
    unittest.main()
