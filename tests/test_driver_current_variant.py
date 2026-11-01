# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from driver_current_variant import source_variant, TOP
from driver_restore_variant import source_variant as restored
from layout import circuits
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]


class DriverCurrentVariant(unittest.TestCase):
    def test_only_one_mirror_finger_is_added_to_the_restored_driver(self):
        original = (ROOT/'analog/openlvds.spice').read_text()
        baseline = restored(original); candidate = source_variant(original)
        before = circuits(baseline); after = circuits(candidate)
        self.assertEqual(set(before), set(after))
        for top in before:
            if top != TOP:
                self.assertEqual(before[top], after[top])
        rows = after[TOP][1]
        added = next(r for r in rows if r[0] == 'XIT10')
        self.assertEqual([r for r in rows if r[0] != 'XIT10'], before[TOP][1])
        self.assertEqual(added[1:], (['TOP', 'PB', 'VDDIO', 'VDDIO'],
            'sky130_fd_pr__pfet_g5v0d10v5', dict(w='20', l='1')))
        self.assertEqual(closure_hash(baseline, 'lvds_bias'), closure_hash(candidate, 'lvds_bias'))

    def test_changed_original_mirror_or_repeated_application_is_rejected(self):
        source = (ROOT/'analog/openlvds.spice').read_text()
        for changed in [source.replace('XIT9 TOP', 'XIT8 TOP'),
                        source.replace('XIT9 TOP PB', 'XIT9 TOP NB'), source_variant(source)]:
            with self.assertRaises(ValueError):
                source_variant(changed)


if __name__ == '__main__':
    unittest.main()
