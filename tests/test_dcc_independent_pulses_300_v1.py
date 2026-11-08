# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_independent_pulses_300_v1 as p
import dcc_chain_measure_300_v2 as original
import test_dcc_chain_measure_300_v2 as fixtures
from replay_bank_300_v2 import same


class IndependentPulseTests(unittest.TestCase):
    def test_all_metrics_preserve_valid_and_first_event_failure_results(self):
        helper=fixtures.PulseHoldTests()
        for changes in ({},dict(repeat=True),dict(release=True),dict(unarmed=True)):
            with self.subTest(changes=changes):
                args=helper.fixture(**changes)
                a=original.pulse_generator(*args);b=p.pulse_generator(*args)
                self.assertTrue(same(a,b));self.assertEqual(b['pulse_generator_integrity_passed'],not bool(changes))

    def test_empty_held_interval_cannot_pass(self):
        args=list(fixtures.PulseHoldTests().fixture())
        # Move the clock fall inside the guard around the internal pulse end.
        t=args[0];args[1][(t>2405)&(t<4500)]=0
        a=original.pulse_generator(*args);b=p.pulse_generator(*args)
        self.assertTrue(same(a,b));self.assertFalse(b['pulse_generator_integrity_passed'])
        self.assertEqual(b['events'][0]['held_interval_samples'],0)
