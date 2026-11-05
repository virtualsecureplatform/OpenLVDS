# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import moscap_component_rc_bank_v90 as model


class MeasuredFineRCIntegrationTests(unittest.TestCase):
    def fixture(self):
        top = model.physical.name('w084')
        text = model.physical.schematic('w084')
        text = text.replace('XSWN ', 'Xnative17 ').replace('XSWP ', 'Xnative9 ').replace('XCLR ', 'Xnative23 ')
        text = text.replace('Xnative9 CAP ENB ', 'Xnative9 CAP ENB.t2 ')
        text = text.replace('Xnative23 CAP ENB ', 'Xnative23 CAP ENB.t1 ')
        text = text.replace('.ends '+top,
            'Rcontrol0 ENB ENB.t2 5\nRcontrol1 ENB ENB.t1 7\nCguardwire ENB.t2 VSS .5f\n.ends '+top)
        return top, text

    def test_renumbered_native_switches_are_found_by_logical_gate_not_width_or_old_name(self):
        top, text = self.fixture()
        found = {r['instance']: r['control_port'] for r in model.fine_pattern(text, top)}
        self.assertEqual(found, dict(Xnative17='EN', Xnative9='ENB', Xnative23='ENB'))
        # The 0.84 um capacitor PMOS has the switch PMOS's W/L, but is data.
        self.assertNotIn('XGCP', found)

    def test_collapse_respects_subcircuit_local_node_names(self):
        top, text = self.fixture()
        unrelated = '.subckt unrelated A VDD VSS\nRbad ENB VDD 1\n.ends unrelated\n'
        self.assertEqual(model.fine_pattern(unrelated+text, top), model.fine_pattern(text, top))

    def test_changed_control_guard_is_rejected(self):
        top, text = self.fixture()
        with self.assertRaisesRegex(ValueError, 'guard'):
            model.fine_pattern(text.replace('XGUARD ENB VSS', 'XGUARD CAP VSS'), top)

    def test_capacitor_wired_to_program_control_is_rejected(self):
        top, text = self.fixture()
        bad = text.replace('XGCP VDD CAP VDD VDD', 'XGCP VDD ENB VDD VDD')
        with self.assertRaisesRegex(ValueError, 'programming-switch'):
            model.fine_pattern(bad, top)

    def test_rc_junction_geometry_is_not_transferred_between_widths(self):
        top, text = self.fixture()
        changed = text.replace(top, model.physical.name('w042'))
        with self.assertRaisesRegex(ValueError, 'dimensions differ'):
            model.transform('', 'w042', changed)


if __name__ == '__main__':
    unittest.main()
