# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v7 as circuit
import probe_static_phase_clock_release_v7 as pilot
import verify_static_phase_clock_release_v7 as verification


class WholeCounterTests(unittest.TestCase):
    def test_wrapper_maps_all_real_observation_ports_and_adds_no_devices(self):
        order=['armed','RESET_N','request_i','VGND','CLK','low0','REQUEST','VPWR','high1','PREPARE','low1']
        rc={circuit.MODEL:dict(info=dict(ports=order))};text=circuit.source(rc,'backend')
        rows=text.splitlines();self.assertEqual(len(rows),3)
        self.assertEqual(rows[1],'Xcore '+' '.join(order)+' '+circuit.MODEL)
        self.assertNotIn('V=',text);self.assertNotIn('.ic',text)
        for missing in circuit.OBSERVATIONS:
            bad={circuit.MODEL:dict(info=dict(ports=[p for p in order if p!=missing]))}
            with self.assertRaises(ValueError):circuit.source(bad,'backend')

    def test_full_counter_profile_still_requires_every_duty_and_stop_case(self):
        specs=pilot.specifications();self.assertEqual(len(specs),4)
        self.assertEqual({(s['duty'],s['stop_level']) for s in specs},{(.4,0),(.4,1),(.6,0),(.6,1)})
        good=dict(counter_feasibility_passed=True,terminal_stress=[dict(max_terminal_difference_v=1.9)],margin_to_next_half_phase_ps=dict(prepare=400,public_release=600))
        rows=[dict(task=dict(spec=s),result=good,error=None) for s in specs]
        self.assertTrue(verification.assess(rows)[0]['source_counter_feasibility_passed'])
        rows[2]=dict(rows[2],result=None,error='Phase ordering failed')
        self.assertFalse(verification.assess(rows)[0]['source_counter_feasibility_passed'])


if __name__=='__main__':unittest.main()
