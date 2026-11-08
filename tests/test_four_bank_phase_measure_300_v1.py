# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import four_bank_phase_measure_300_v1 as p
import test_two_bank_native_measure_300_v1 as fixtures


class PhaseGridTests(unittest.TestCase):
    def fixture(self,delays):
        helper=fixtures.RelativeTransportTests();helper.setUp()
        waves={node:helper.wave(delay) for node,delay in zip(p.NODES,delays)}
        return helper.t,waves.__getitem__,helper.s

    def test_exact_quarters_reproduce_unwrapped_full_period(self):
        quarter=1e6/310/4
        r=p.measure(*self.fixture([k*quarter for k in range(5)]))
        self.assertTrue(r['observed_50ps_phase_grid_passed']);self.assertTrue(r['observed_20ps_period_closure_passed'])
        self.assertFalse(r['qualified_phy'])
        np.testing.assert_allclose(r['edges']['rise']['unwrapped_phase_offsets_ps']['B3_OUT'],4*quarter,atol=1e-6)

    def test_transport_and_full_period_closure_cannot_hide_bad_intermediate_phase(self):
        quarter=1e6/310/4
        r=p.measure(*self.fixture([0,quarter+80,2*quarter,3*quarter,4*quarter]))
        self.assertTrue(r['observed_20ps_period_closure_passed'])
        self.assertFalse(r['observed_50ps_phase_grid_passed'])
        self.assertAlmostEqual(r['edges']['rise']['maximum_phase_grid_error_ps'],80,6)

    def test_missing_startup_and_full_cycle_alias_are_rejected(self):
        quarter=1e6/310/4
        t,get,s=self.fixture([0,quarter,2*quarter,3*quarter,8*quarter])
        r=p.measure(t,get,s);self.assertFalse(r['observed_20ps_period_closure_passed'])
        helper=fixtures.RelativeTransportTests();helper.setUp()
        waves={n:get(n) for n in p.NODES};waves['OUT']=helper.wave(quarter,missing_first=True)
        r=p.measure(t,waves.__getitem__,s)
        self.assertFalse(r['all_startup_events_present']);self.assertFalse(r['observed_50ps_phase_grid_passed'])
