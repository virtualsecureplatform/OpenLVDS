# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_mux_tree_access_v3 import unchanged_masks


class MuxMaskIsolationTests(unittest.TestCase):
    ORIGINAL = 'magic\ntech sky130A\n<< locali >>\nrect 0 0 40 40\n<< labels >>\nrlabel locali 2 2 2 2 0 X\nport 1 nsew\n<< properties >>\nstring FIXED_BBOX 0 0 100 100\n<< end >>\n'

    def test_only_extraction_labels_may_change(self):
        labelled = self.ORIGINAL.replace('<< labels >>\n', '<< labels >>\nrlabel locali 20 20 20 20 0 LI_0\n')
        self.assertTrue(unchanged_masks(self.ORIGINAL, labelled))
        for changed in (labelled.replace('rect 0 0 40 40', 'rect 0 0 41 40'),
                        labelled.replace('100 100', '101 100'),
                        labelled.replace('<< locali >>', '<< metal1 >>')):
            self.assertFalse(unchanged_masks(self.ORIGINAL, changed))

    def test_missing_or_duplicated_label_section_rejected(self):
        for text in (self.ORIGINAL.replace('<< labels >>', ''), self.ORIGINAL+'<< labels >>\n'):
            with self.assertRaises(ValueError):
                unchanged_masks(self.ORIGINAL, text)


if __name__ == '__main__':
    unittest.main()
