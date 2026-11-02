# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_receiver_amplifier_transport as observation


class AmplifierTransportObservation(unittest.TestCase):
    def test_printed_bus_must_be_unique_and_explicit(self):
        header={'V(XRC:OPENLVDS_RECEIVER_CORE__AMP_OUT)':4}
        self.assertEqual(observation.amplifier_column(header, 'AMP_OUT'), 4)
        with self.assertRaises(ValueError): observation.amplifier_column(header, 'AMP_L')
        header['V(XRC:OPENLVDS_RECEIVER_CORE__AMP_OUT.T2)']=5
        with self.assertRaises(ValueError): observation.amplifier_column(header, 'AMP_OUT')

    def test_each_stage_is_measured_independently_with_original_window(self):
        t=np.arange(9)*1e-9
        nodes=dict(CO=np.array([-.1,-.1,-.1,.1,.1,.1,.1,.1,.1]), CL=np.zeros(9),
            AMP_OUT=np.array([.7,.7,.7,.7,.9,.9,.9,.9,.9]), CO_TRACK=np.full(9,.8),
            RESTORE0=np.array([1.8,1.8,1.8,1.8,1.8,0,0,0,0]),
            RESTORE1=np.array([0,0,0,0,0,0,1.8,1.8,1.8]),
            RXCLOCK=np.array([1.8,1.8,1.8,1.8,1.8,1.8,1.8,0,0]))
        windows=[dict(input_edge_ns=1, response_window_end_ns=6, output_edges_in_next_input_period=0)]
        row=observation.stage_windows(t,nodes,windows)[0]
        for name,latency in [('decision',1500),('amplifier',2500),('restore0',3500),('restore1',4500)]:
            self.assertEqual(row['stages'][name]['crossing_count'],1)
            self.assertAlmostEqual(row['stages'][name]['latencies_ps'][0],latency)
        self.assertEqual(row['stages']['output']['crossing_count'],0)
        self.assertEqual(row['output_edges_in_next_input_period'],0)
        self.assertAlmostEqual(row['ranges']['amplifier_reference_difference']['max_v'],.1)

    def test_finite_increasing_and_nonempty_observations_are_required(self):
        t=np.arange(3)*1e-9
        nodes={k:np.zeros(3) for k in ['CO','CL','AMP_OUT','CO_TRACK','RESTORE0','RESTORE1','RXCLOCK']}
        for times in [np.array([0,1e-9,1e-9]),np.array([0,np.nan,2e-9])]:
            with self.assertRaises(ValueError): observation.stage_windows(times,nodes,[])
        with self.assertRaises(ValueError):
            observation.stage_windows(t,nodes,[dict(input_edge_ns=4,response_window_end_ns=5)])
        nodes['AMP_OUT'][0]=np.nan
        with self.assertRaises(ValueError): observation.stage_windows(t,nodes,[])


if __name__=='__main__':unittest.main()
