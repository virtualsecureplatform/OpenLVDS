# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_counter_protocol_300 as fixtures
import counter_protocol_300 as old
import counter_protocol_300_v2 as new

class ClearSettling300Tests(unittest.TestCase):
    def test_restores_three_ns_settling_without_changing_stimulus(self):
        t,v,s=fixtures.Counter300Tests().waves()
        for n in ('XD:XR:low1','XD:XR:armed'):v[n][(t>=30000)&(t<30500)]=.4
        self.assertFalse(old.timing(t,v.__getitem__,s)['timing_protocol_passed'])
        r=new.timing(t,v.__getitem__,s)
        self.assertTrue(r['timing_protocol_passed'])
        self.assertEqual(r['stopped_clock_clear_start_ps'],31000)
        self.assertEqual(r['stopped_clock_clear_settling_ps'],3000)
    def test_real_late_internal_clear_still_fails(self):
        t,v,s=fixtures.Counter300Tests().waves();v['XD:XR:armed'][(t>=31000)&(t<31500)]=.4
        self.assertFalse(new.timing(t,v.__getitem__,s)['timing_protocol_passed'])
    def test_public_clear_uses_same_original_three_ns_allowance(self):
        t,v,s=fixtures.Counter300Tests().waves();v['RESET_N'][(t>=30000)&(t<30500)]=.4
        self.assertFalse(old.timing(t,v.__getitem__,s)['stopped_clock_clear_and_reassert_passed'])
        self.assertTrue(new.timing(t,v.__getitem__,s)['stopped_clock_clear_and_reassert_passed'])
        v['RESET_N'][(t>=31000)&(t<31500)]=.4
        self.assertFalse(new.timing(t,v.__getitem__,s)['stopped_clock_clear_and_reassert_passed'])
    def test_all_other_original_timing_metrics_are_identical(self):
        for f in (290,300,310):
            for d in (.4,.5,.6):
                for level in (0,1):
                    t,v,s=fixtures.Counter300Tests().waves(f,d,level)
                    expected=old.timing(t,v.__getitem__,s);actual=new.timing(t,v.__getitem__,s)
                    self.assertEqual({k:actual[k] for k in expected},expected)
