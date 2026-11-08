# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_independent_events_300_v1 as p
import dcc_chain_measure_300_v1 as original
import test_dcc_chain_measure_300_v1 as fixtures
from replay_bank_300_v2 import same


class IndependentEventsTests(unittest.TestCase):
    def test_all_metrics_agree_for_valid_unbalanced_and_missing_events(self):
        helper=fixtures.DccEventTests()
        for args in ({},dict(spacing=1e6/310/2),dict(drop_first=True)):
            with self.subTest(args=args):
                t,clocks,q,s=helper.fixture(**args)
                self.assertTrue(same(original.events(t,*clocks,q,s),p.events(t,*clocks,q,s)))

    def test_wrong_initial_level_and_late_transition_remain_failed(self):
        helper=fixtures.DccEventTests();t,clocks,q,s=helper.fixture();q[0]=0
        a=original.events(t,*clocks,q,s);b=p.events(t,*clocks,q,s)
        self.assertTrue(same(a,b));self.assertFalse(b['one_transition_per_source_event_passed'])
        # Delay every output transition beyond the next opposite source event.
        t,clocks,q,s=helper.fixture();q=helper.wave(t,[(x+1800,k%2==1) for k,x in enumerate(sorted(
            [2100+j*1e6/310 for j in range(8)]+[3600+j*1e6/310 for j in range(8)]))],1.8)
        a=original.events(t,*clocks,q,s);b=p.events(t,*clocks,q,s)
        self.assertTrue(same(a,b));self.assertFalse(b['one_transition_per_source_event_passed'])
