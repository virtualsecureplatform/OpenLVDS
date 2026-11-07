# SPDX-License-Identifier: GPL-3.0-only
"""Reject incomplete or changed capacitor geometry before fresh RC extraction."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
try:
    import qualify_counter_output_mim5_rc_v337 as rc
except ModuleNotFoundError as error:
    if error.name != 'klayout':
        raise
    rc = None


@unittest.skipIf(rc is None, 'requires pinned CAD KLayout interpreter')
class NativeCapacitorRcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT/'build/diagnostics/counter_output_mim5_physical_v336/80531cf7f88fa1a5'
        cls.report = json.loads((parent/'summary.json').read_text())
        cls.state = json.loads((parent/'state.json').read_text())

    def test_real_passed_native_material_is_admissible(self):
        rc.require_physical(self.state, self.report)

    def test_failed_or_partial_physical_material_is_rejected(self):
        for state in (dict(status='building', qualified_phy=False),
                      dict(status='complete', passed=False, qualified_phy=False)):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, 'complete passing'):
                rc.require_physical(state, self.report)

    def test_changed_inventory_masks_labels_or_dimensions_are_rejected(self):
        changes = [('native_mos', None, 1), ('native_mim', None, 2),
                   ('native_inventory', 'all_native_model_dimensions_preserved', False),
                   ('native_inventory', 'native_model_counts', {rc.physical.CAP: 2}),
                   ('physical', 'drc_count', '1'), ('physical', 'lvs_passed', False),
                   ('native_masks', 'all_native_masks_preserved', False),
                   ('whole_masks', 'all_native_masks_preserved', False),
                   ('native_labels', 'all_native_labels_preserved', False)]
        for key, nested, value in changes:
            report = copy.deepcopy(self.report)
            if nested is None:
                report[key] = value
            else:
                report[key][nested] = value
            with self.subTest(key=key, nested=nested), self.assertRaisesRegex(ValueError, 'complete passing'):
                rc.require_physical(self.state, report)


if __name__ == '__main__':
    unittest.main()
