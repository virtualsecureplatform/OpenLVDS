# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_forward_pair_v2 as pilot
import verify_forward_pair_v2 as verifier


class ForwardPairTests(unittest.TestCase):
    def wave(self,glitch=False,overstress=False,stuck=False):
        spec=pilot.specifications()[0];t=np.arange(20001)*1e-12
        values=dict(a=np.full(len(t),1.8),b=pilot.stimulus(t,spec),y=1.8-pilot.stimulus(t-50e-12,spec),vdd=np.full(len(t),1.8))
        if glitch:values['y'][600:610]=0.
        if overstress:values['y'][2125]=2.05
        if stuck:values['y'][(t>3.6e-9)&(t<5.9e-9)]=1.8
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t,*values.values()])

    def measured(self,**kw):
        devices=[dict(name='XG:test',model='sky130_fd_pr__nfet_01v8',terminals=['Y','A','0','0'],limit_v=1.95)]
        with patch.object(pilot,'validate',return_value=self.wave(**kw)):
            return pilot.measure(Path('/fixture'),pilot.specifications()[0],devices)

    def test_output_events_settling_and_all_transient_terminal_stress_are_required(self):
        good=self.measured()
        self.assertTrue(good['isolated_pilot_passed'])
        self.assertEqual([e['output_edge'] for e in good['events']],['fall','rise','fall','rise'])
        for event in good['events']:self.assertAlmostEqual(event['delay_ps'],50.,places=6)
        self.assertFalse(self.measured(glitch=True)['event_integrity_passed'])
        self.assertFalse(self.measured(overstress=True)['terminal_screen_passed'])
        self.assertFalse(self.measured(stuck=True)['logic_passed'])

    def test_fixed_supply_and_exact_matched_input_are_checked(self):
        names,w=self.wave();w[:,names.index('v(vdd)')]=1.79
        with patch.object(pilot,'validate',return_value=(names,w)):
            with self.assertRaises(ValueError):pilot.measure(Path('/fixture'),pilot.specifications()[0],[])

    def test_real_port_order_and_both_input_orientations_remain_in_the_decks(self):
        self.assertEqual([(s['variant'],s['toggle_pin']) for s in pilot.specifications()],
                         [('shunted','B'),('shunted','A'),('original','B'),('original','A')])
        for spec in pilot.specifications():
            with patch.dict(os.environ,PDK_ROOT='/pdk'):
                deck=pilot.fixture(Path('/fixture'),spec,['Y','VGND','B','VPWR','A'],[])
            self.assertIn('XG Y 0 B VDD A '+pilot.MODELS[spec['variant']],deck)
            self.assertIn('VDD VDD 0 1.8',deck)
            self.assertIn('.tran 1p 20n 0 1p',deck)
            self.assertIn('.options itl4=100',deck)

    def test_failed_reference_never_supplies_timing_or_hides_a_shunted_failure(self):
        result=self.measured()
        rows=[dict(task=dict(spec=s),result=deepcopy(result),error=None) for s in pilot.specifications()]
        rows[2].update(result=None,error='retained completed timestep collapse')
        groups,comparison=verifier.assess(rows)
        self.assertTrue(groups[0]['isolated_pilot_passed']);self.assertFalse(groups[1]['isolated_pilot_passed'])
        self.assertFalse(comparison[0]['timing_comparison_available']);self.assertIsNone(comparison[0]['shunted_minus_original_delay_ps'])
        rows[0]['result']['isolated_pilot_passed']=False
        self.assertFalse(verifier.assess(rows)[0][0]['isolated_pilot_passed'])
        with self.assertRaises(ValueError):verifier.assess(rows[:-1])
