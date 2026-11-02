# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_spec_screen as screen
import receiver_later_buffers as buffers
from dll_campaign import text_block
from layout import circuits,flatten
import receiver_tia_restore as tia

ROOT=Path(__file__).resolve().parents[1]


class ReceiverSpecificationScreen(unittest.TestCase):
    def test_finite_coverage_and_unchanged_final_requirements(self):
        req=json.loads((ROOT/'requirements.json').read_text());tasks=screen.cases(req)
        self.assertEqual(len(tasks),33);self.assertEqual(len({t['id'] for t in tasks}),33)
        self.assertEqual({t['mhz'] for t in tasks if t['test']=='rate'},{390,400,410})
        for view in ['schematic','native']:
            self.assertEqual({(t['process'],t['temperature']) for t in tasks if t['view']==view and t['test']=='wide'},
                             {(p,t) for p in req['process_corners'] for t in req['temperatures_c']})
        p=screen.policy();self.assertEqual(p['static_threshold_v'],req['rx_threshold_v'])
        self.assertEqual(p['release_requires']['minimum_sampling_margin_ps'],req['minimum_sampling_margin_ps'])
        self.assertEqual(p['release_requires']['nominal_payload_bits'],req['minimum_extracted_nominal_bits'])
        self.assertEqual(p['release_requires']['minimum_training_cycles'],256)

    def test_pin_slew_is_twenty_to_eighty_not_full_ramp(self):
        p,n=screen.pin_wave([(5,1),(6.2,0)],0,.25,1.2,260)
        import re
        vals=[float(v.rstrip('n')) for v in re.findall(r'[-0-9.]+n?',p[4:-1])]
        self.assertAlmostEqual((vals[4]-vals[2])*.6*1000,260,places=5)
        self.assertIn('1.325',p);self.assertIn('1.075',p)
        self.assertNotEqual(p,n)
        with self.assertRaisesRegex(ValueError,'Overlapping'):screen.pin_wave([(0.1,1)],0,.25,1.2,260)

    def test_crossing_without_valid_level_is_not_a_valid_pulse(self):
        t=np.linspace(0,10e-9,10001)
        v=np.where((t%2e-9)<1e-9,1.0,0.0)
        result=screen.valid_widths(t,v,2e-9,9e-9)
        self.assertEqual(result['high']['count'],0)
        v=np.where((t%2e-9)<.1e-9,1.8,0.0)
        result=screen.valid_widths(t,v,2e-9,9e-9)
        self.assertLess(result['high']['minimum_ps'],110)

    def test_wide_dc_checks_both_outputs_each_polarity_and_trace_completeness(self):
        t=np.linspace(0,72e-9,7201);w=np.zeros((len(t),10));w[:,1]=t
        names=['RP','RN','RCP','RCN','RXCLOCK','RXDATA','Q0','Q1']
        h={'V('+n+')':i+2 for i,n in enumerate(names)}
        w[:,2:6]=1.2
        w[:,6]=w[:,7]=1.8*(np.floor(t/12e-9).astype(int)%2)
        self.assertTrue(screen.measure(w,h,dict(test='wide'))['passed'])
        w[:,7]=0
        self.assertFalse(screen.measure(w,h,dict(test='wide'))['passed'])
        with self.assertRaisesRegex(ValueError,'Incomplete'):screen.measure(w[:-2],h,dict(test='wide'))


class BoundedLaterBuffers(unittest.TestCase):
    def setUp(self):self.source=tia.source_variant((ROOT/'analog/openlvds.spice').read_text(),'tia_r2')

    def devices(self,source):return flatten(circuits(source),buffers.TOP)[1]

    def test_baseline_exact_and_earlier_chain_preserved_in_both_alternatives(self):
        self.assertEqual(buffers.transform(self.source,'baseline'),self.source)
        base={d['name']:d for d in self.devices(self.source)}
        protected={n:d for n,d in base.items() if '__XIB1__' not in n and '__XIB2__' not in n}
        for variant in buffers.VARIANTS[1:]:
            candidate=buffers.transform(self.source,variant);ds={d['name']:d for d in self.devices(candidate)}
            self.assertTrue(all(ds[n]==d for n,d in protected.items()))
            self.assertEqual(text_block(candidate,'lvds_inv18_drive'),text_block(self.source,'lvds_inv18_drive'))

    def test_parallel_unit_counts_and_skew_are_exact(self):
        base=len(self.devices(self.source))
        self.assertEqual(len(self.devices(buffers.transform(self.source,'symmetric_taper'))),base+12)
        self.assertEqual(len(self.devices(buffers.transform(self.source,'skewed_buffers'))),base+3)
        with self.assertRaises(ValueError):buffers.transform(self.source,'another_sweep')
        with self.assertRaises(ValueError):buffers.transform(self.source.replace('XRFB1 ','XOTHER '),'baseline')


if __name__=='__main__':unittest.main()
