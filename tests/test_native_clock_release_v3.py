# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_clock_release_v3 as release
import test_native_clock_release_v2 as previous


class DirectRequestReleaseTests(unittest.TestCase):
    def test_two_new_edges_are_required_even_after_reset_with_stopped_clock(self):
        with patch.object(previous,'release',release):
            previous.StaticClockReleaseTests().test_async_internal_clear_and_two_new_edges_after_clock_stop()

    def test_first_stage_has_no_redundant_tied_input_nand(self):
        cells={name:(model,pins) for name,model,pins in release.gates()}
        self.assertEqual(len(cells),23)
        self.assertEqual(cells['r0_data_n'],('inv_1',dict(A='REQUEST',Y='r0_dn')))
        self.assertNotIn('r0_data',cells)
        self.assertEqual(cells['r0_master_s'][1]['A'],'REQUEST')
        self.assertEqual(cells['r1_data_n'][0],'nand2_2')
        self.assertEqual(sum(model=='nand3_2' and pins['C']=='REQUEST' for model,pins in cells.values()),4)


if __name__=='__main__':unittest.main()
