# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from dll_design import candidate_source
from repair_dll_monitor import repaired_source
from screen_fast_reset_dll import candidate_source as fast_reset_source
from rebind_dll_pfd_source import compatible

ROOT = Path(__file__).resolve().parents[1]


class DLLSourceRebinding(unittest.TestCase):
    def sources(self):
        original = repaired_source(candidate_source((ROOT / 'analog/openlvds.spice').read_text(), 'ota_w8_c4',
                                   (ROOT / 'analog/experiments/phase_area.spice').read_text()))
        return original, fast_reset_source(original)

    def test_pfd_only_change_preserves_the_full_analog_scope(self):
        original, proposed = self.sources(); scope, ports = compatible(original, proposed)
        self.assertEqual(len(ports), 15)
        self.assertIn('openlvds_dll_analog__XAREA__XPOS__', scope)
        self.assertNotIn('sky130_fd_sc_hd__a22oi_4', scope)

    def test_analog_connection_or_global_option_changes_require_new_layout(self):
        original, proposed = self.sources()
        changed = proposed.replace('XRP0 VDDD PRE', 'XRP0 VDDD CTRL')
        self.assertNotEqual(changed, proposed)
        for invalid in [changed, '.options scale=0.001\n' + proposed]:
            with self.assertRaisesRegex(ValueError, 'outside the PFD'):
                compatible(original, invalid)

    def test_pfd_public_interface_cannot_change(self):
        original, proposed = self.sources()
        invalid = proposed.replace('.subckt lvds_pfd REF FB', '.subckt lvds_pfd REF_CHANGED FB')
        self.assertNotEqual(invalid, proposed)
        with self.assertRaisesRegex(ValueError, 'public interface'):
            compatible(original, invalid)

    def test_unchanged_and_duplicate_definitions_are_rejected(self):
        original, proposed = self.sources()
        with self.assertRaisesRegex(ValueError, 'No PFD source update'):
            compatible(original, original)
        with self.assertRaisesRegex(ValueError, 'Duplicate source'):
            compatible(original, proposed + '\n.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\n.ends lvds_pfd\n')
