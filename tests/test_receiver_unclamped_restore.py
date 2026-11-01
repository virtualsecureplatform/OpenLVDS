# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from receiver_unclamped_restore_experiment import source_variant
from receiver_fast_restore_experiment import source_variant as previous_source
from receiver_static_diagnosis import remove_clamps


class UnclampedRestoration(unittest.TestCase):
    def test_source_is_identical_to_passing_matched_static_intervention(self):
        source = (Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text()
        result = source_variant(source)
        self.assertEqual(result, remove_clamps(previous_source(source)))
        self.assertNotIn('XCLAMP0 ', result)
        self.assertNotIn('XCLAMP1 ', result)
        self.assertIn('XIB0 CO RESTORE0 VDDD VSS lvds_rx_restore_mid', result)
        self.assertIn('XIB1 RESTORE0 RESTORE1 VDDD VSS lvds_inv18_drive', result)
        self.assertIn('XIB2 RESTORE1 Q VDDD VSS lvds_inv18_drive', result)
        self.assertEqual(source_variant(source, False), previous_source(source, False))


if __name__ == '__main__':
    unittest.main()
