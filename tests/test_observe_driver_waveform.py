# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_driver_waveform as observation


class LoadedDriverWaveformObservation(unittest.TestCase):
    def waveform(self,ramp=.5,ripple=0):
        ns=np.r_[0,1801,1850,1889,1951,1970,1989,np.arange(1999,2502,.005),2540]
        phase=(ns-2000)%2.5
        voltage=np.interp(phase,[0,ramp/2,1.25-ramp/2,1.25+ramp/2,2.5-ramp/2,2.5],[0,-.35,-.35,.35,.35,0])
        voltage[ns<1900]=-.35;voltage[(ns>1900)&(ns<1990)]=.35
        common=1.25+ripple*np.sin(2*np.pi*phase/2.5)
        return np.column_stack([np.arange(len(ns)),ns*1e-9,common+voltage/2,common-voltage/2]),{'V(P)':2,'V(N)':3}

    def test_twenty_eighty_uses_complete_differential_state_to_state_span(self):
        result=observation.measure(*self.waveform())
        self.assertEqual(result['edges'],392)
        self.assertAlmostEqual(result['transition_min_ps'],300,places=5)
        self.assertAlmostEqual(result['transition_max_ps'],300,places=5)
        self.assertTrue(result['transition_within_reference_limits'])
        self.assertTrue(result['monotonic_20_80'])

    def test_full_common_mode_ripple_is_seen_even_with_correct_midpoint(self):
        result=observation.measure(*self.waveform(ripple=.4))
        self.assertAlmostEqual(result['common_mode_pp_v'],.8)
        self.assertFalse(result['common_mode_within_reference_limit'])
        self.assertTrue(result['transition_within_reference_limits'])

    def test_fast_and_slow_edges_are_reported_separately_from_component_pass(self):
        for ramp in [.2,.8]:
            result=observation.measure(*self.waveform(ramp=ramp))
            self.assertFalse(result['transition_within_reference_limits'])
            self.assertNotIn('passed',result)

    def test_incomplete_and_constant_output_cannot_produce_an_observation(self):
        w,h=self.waveform()
        with self.assertRaisesRegex(ValueError,'Incomplete'):observation.measure(w[:-1],h)
        w[:,2:]=1.25
        with self.assertRaisesRegex(ValueError,'polarity'):observation.measure(w,h)

    def test_unrelated_artifact_cannot_be_observed(self):
        with self.assertRaises(ValueError):observation.observe(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
