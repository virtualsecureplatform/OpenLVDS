# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_path_timing_300_v1 as p
import test_dcc_source_measure_300_v2 as source_fixture
from replay_bank_300_v2 import same


class DCCPathTimingTests(unittest.TestCase):
    def fixture(self,delay):
        names,w,s=source_fixture.CompleteDCCSourceTests().fixture(extra_f_delay=delay)
        t=w[:,0]*1e12;events=np.sort(np.r_[p.source.inputs.edge_times(t,w[:,names.index('v(p0)')],.9,True,False),
            p.source.inputs.edge_times(t,w[:,names.index('v(p180)')],.9,True,False)])
        qt=np.zeros(len(t))
        for k,x in enumerate(events):qt+=(1 if k%2==0 else -1)*1.8*np.clip(.5+(t-x-100)/40,0,1)
        return names+['v(xd.qt)'],np.column_stack((w,qt)),s

    def test_full_epoch_decomposition_and_known_output_stage_bias(self):
        for delay in (0,80):
            names,w,s=self.fixture(delay);a=p.measure(names,w,s);b=p.measure(names,w,s,independent=True)
            self.assertTrue(same(a,b));self.assertAlmostEqual(a['reconstructed_mean_half_cycle_error_ps'],delay,places=6)
            self.assertAlmostEqual(a['mean_phase180_minus_phase0_stage_ps']['toggle_to_output'],delay,places=6)
            self.assertEqual(a['original_source_screen_passed'],delay<=50)
            for row in a['paths'].values():self.assertEqual(len(row['source_to_output_ps']),18)
            self.assertFalse(a['timing_modified']);self.assertFalse(a['qualified_phy'])

    def test_missing_toggle_startup_event_refused_despite_unchanged_final_clock(self):
        names,w,s=self.fixture(0);bad=w.copy();bad[w[:,0]*1e12<4500,names.index('v(xd.qt)')]=0
        with self.assertRaisesRegex(ValueError,'path event'):p.measure(names,bad,s)
        with self.assertRaisesRegex(ValueError,'toggle-FF'):p.measure(names[:-1],w[:,:-1],s)
