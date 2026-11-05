# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_mux_tree_access_v4 as probe


class NativeDiffusionLabelTests(unittest.TestCase):
    TEXT = ('magic\ntech sky130A\n<< ndiff >>\nrect 0 0 40 40\n'
            '<< pdiff >>\nrect 100 100 140 140\n'
            '<< metal1 >>\nrect 0 0 200 200\n'
            '<< locali >>\nrect 100 100 140 140\n'
            '<< labels >>\nrlabel metal1 50 50 50 50 0 A\nport 1 nsew\n<< end >>\n')

    def test_native_layer_selected_without_using_overlapping_metal(self):
        labelled, points = probe.annotate(self.TEXT, {'a_0_0#': 'MID0', 'a_100_100#': 'MID1'})
        self.assertIn('rlabel ndiff 2 2 2 2 0 MID0', labelled)
        self.assertIn('rlabel pdiff 102 102 102 102 0 MID1', labelled)
        self.assertNotIn('rlabel metal1 102 102', labelled)
        self.assertTrue(probe.unchanged_masks(self.TEXT, labelled))
        self.assertEqual(len(points), 1)

    def test_absent_or_ambiguous_native_diffusion_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.annotate(self.TEXT, {'a_50_50#': 'MID0'})
        overlap = self.TEXT.replace('<< pdiff >>\n', '<< pdiff >>\nrect 0 0 40 40\n')
        with self.assertRaises(ValueError):
            probe.annotate(overlap, {'a_0_0#': 'MID0'})


if __name__ == '__main__':
    unittest.main()
