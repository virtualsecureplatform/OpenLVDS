# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_native_ff_reset_guards_v2 as diagnosis
import probe_guarded_clock_prepare_v3 as extended
import test_guarded_clock_prepare_pilot_v2 as original


class NativeFfResetGuardTests(unittest.TestCase):
    def test_third_ff_reset_excursion_keeps_actual_nodes_and_private_target(self):
        values={'0':np.array([0.,0.]),'VDD':np.array([1.8,1.8]),'XD:XR:r2__reset_node':np.array([0.,-.4])}
        ds=[dict(name='XD:XR:Xr2__X9',model='sky130_fd_pr__special_nfet_01v8',limit_v=1.95,
                 terminals=['0','VDD','XD:XR:r2__reset_node','0'])]
        r=diagnosis.inspect(np.array([0.,1.]),values.__getitem__,ds)
        self.assertEqual(r['private_nodes'],['reset_node'])
        self.assertIn('XD:XR:r2__reset_node',r['violations'][0]['nodes'])
        self.assertFalse(r['uncovered_violations'])

    def test_extended_counter_preserves_clock_count_and_stopped_reassertion_checks(self):
        with patch.object(original,'pilot',extended):
            original.GuardedPreparePilotTests().test_prepare_after_two_and_public_release_after_three_with_both_stop_levels()
            original.GuardedPreparePilotTests().test_stopped_clock_reassertion_and_late_stress_cannot_be_hidden()


if __name__=='__main__':unittest.main()
