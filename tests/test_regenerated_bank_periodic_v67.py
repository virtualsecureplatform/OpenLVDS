# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerated_bank_periodic_measure_v67 as p


class NativePeriodicTimingTests(unittest.TestCase):
    def fixture(self,duty=.4,fine=0,delay=550,width=80):
        s=dict(coarse=0,fine=fine,frequency_mhz=410,duty=duty,cycles=8)
        t=np.arange(0,25001,2);period=1e6/410
        def wave(offset,edge_width):
            return sum(.9*(np.tanh((t-(2100+k*period+offset))/edge_width)-
                       np.tanh((t-(2100+(k+duty)*period+offset))/edge_width)) for k in range(8))
        return s,t,wave(0,45.51196133134187),wave(delay,width)

    def test_both_input_duties_keep_all_unwrapped_edges(self):
        for duty in (.4,.6):
            s,t,a,b=self.fixture(duty=duty);r=p.timing(t,a,b,s)
            for key in ('all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed',
                'unwrapped_native_epoch_passed','period_screen_passed','repeated_delay_screen_passed','zero_code_quarter_passed'):
                self.assertTrue(r[key],key)
            self.assertEqual(len(r['output_duty_percent']),8)
            self.assertTrue(r['current_downstream_250ps_slew_domain_passed'])

    def test_slow_full_swing_clock_requires_wider_downstream_domain(self):
        s,t,a,b=self.fixture(fine=31,delay=1100,width=200);r=p.timing(t,a,b,s)
        self.assertTrue(r['full_swing_pulses_passed']);self.assertTrue(r['unwrapped_native_epoch_passed'])
        self.assertTrue(r['downstream_slew_domain_widening_required'])
        self.assertFalse(r['current_downstream_250ps_slew_domain_passed'])
        self.assertTrue(r['zero_code_quarter_passed']);self.assertFalse(r['zero_code_quarter_check_required'])

    def test_zero_code_delay_still_needs_quarter_headroom(self):
        s,t,a,b=self.fixture(delay=700);r=p.timing(t,a,b,s)
        self.assertFalse(r['zero_code_quarter_passed']);self.assertLess(r['zero_code_fast_quarter_headroom_ps'],0)

    def test_wrong_epoch_is_not_accepted_modulo_period(self):
        s,t,a,b=self.fixture(fine=31,delay=550+1e6/410);r=p.timing(t,a,b,s)
        self.assertTrue(r['all_input_output_pulses_present']);self.assertFalse(r['unwrapped_native_epoch_passed'])

    def test_missing_clock_and_half_swing_clock_are_rejected(self):
        s,t,a,b=self.fixture()
        r=p.timing(t,a,np.zeros(len(t)),s)
        self.assertFalse(r['all_input_output_pulses_present']);self.assertIsNone(r['zero_code_fast_quarter_headroom_ps'])
        r=p.timing(t,a,b*.75,s)
        self.assertTrue(r['all_input_output_pulses_present']);self.assertFalse(r['full_swing_pulses_passed'])

    def test_wrong_input_duty_cannot_match_by_edge_count_alone(self):
        s,t,a,b=self.fixture();s['duty']=.6
        r=p.timing(t,a,b,s)
        self.assertTrue(r['all_input_output_pulses_present']);self.assertFalse(r['input_timing_stimulus_passed'])


if __name__=='__main__':unittest.main()
