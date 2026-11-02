# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_receiver_input_contract as observation


class ReceiverInputSupport(unittest.TestCase):
    def test_interpolated_threshold_duration_and_clipped_windows(self):
        t=np.array([0.,2.,4.]);v=np.array([0.,2.,0.])
        self.assertEqual(observation.supported_intervals(t,v,1,0,4),[[1.,3.]])
        self.assertEqual(observation.supported_intervals(t,v,1,1.5,2.5),[[1.5,2.5]])
        self.assertEqual(observation.supported_intervals(t,v,3,0,4),[])
        self.assertEqual(observation.supported_intervals(t,v,2,0,4),[])

    def test_separate_supported_islands_and_finite_complete_interval(self):
        t=np.arange(5.);v=np.array([0.,2.,0.,2.,0.])
        self.assertEqual(observation.supported_intervals(t,v,1,0,4),[[.5,1.5],[2.5,3.5]])
        for times,values,start,end in [(t,v,-1,4),(t,v,0,5),(t,v,1,1),(np.array([0.,0.,2.]),np.zeros(3),0,2),(t,v+np.nan,0,4)]:
            with self.assertRaises(ValueError):observation.supported_intervals(times,values,1,start,end)

    def test_no_dynamic_pass_is_inferred_from_static_threshold(self):
        t=np.arange(5)*1e-9;diff=np.array([0.,-.2,0.,.05,0.])
        report=dict(pulses=[dict(polarity='falling',input_edge_ns=0,input_pulse_width_ps=2000,input_peak_magnitude_v=.2,output_edges_in_next_input_period=0),dict(polarity='rising',input_edge_ns=2,input_pulse_width_ps=2000,input_peak_magnitude_v=.05,output_edges_in_next_input_period=1)])
        rows=observation.pulse_support(t,diff,report,.1)
        self.assertTrue(rows[0]['peak_reaches_sensitivity_threshold']);self.assertAlmostEqual(rows[0]['above_threshold_longest_ps'],1000)
        self.assertEqual(rows[0]['output_edges_in_next_input_period'],0)
        self.assertFalse(rows[1]['peak_reaches_sensitivity_threshold']);self.assertEqual(rows[1]['above_threshold_total_ps'],0)
        self.assertNotIn('passed',rows[0])


if __name__=='__main__':unittest.main()
