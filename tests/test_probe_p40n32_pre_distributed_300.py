# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_p40n32_pre_distributed_300 as p


class P40N32PilotTests(unittest.TestCase):
    def test_zero_first_fresh_numerical_pair_and_complete_coverage(self):
        tasks = p.specifications()
        self.assertEqual(len(tasks), 5)
        self.assertEqual([(t['spec']['coarse'], t['spec']['fine'], t['spec']['duty'])
                          for t in tasks], [(0, 0, .5), (0, 31, .6),
                                           (0, 31, .4), (1, 0, .5), (0, 31, .6)])
        self.assertEqual([t['centered'] for t in tasks], [True, True, True, True, False])
        self.assertEqual(tasks[1]['spec'], tasks[4]['spec'])
        for task in tasks:
            self.assertEqual(task['variant'], p.VARIANT)
            self.assertEqual((task['spec']['frequency_mhz'], task['spec']['stop_ns'],
                              task['spec']['cycles']), (310, 40, 8))

    def test_all_five_native_fixtures_preserve_observations_and_stimulus(self):
        source = json.loads((p.PARENT / 'manifest.json').read_text())['identity']
        _, obs, revision = p.architecture.transform((p.PARENT / 'bank.spice').read_text(),
                                                   source['observations'])
        identity = dict(source_identity=source, observations={p.VARIANT: obs},
                        revisions={p.VARIANT: revision})
        for task in p.specifications():
            deck = p.fixture(p.ROOT / 'build/unused-medium-pre-pilot-300', identity, task)
            self.assertEqual(deck.count('tanh((time-'), 16)
            self.assertEqual(deck.count(p.prior.numerical.CARD), 0)
            self.assertEqual(deck.count(p.numerical_trial.CARD), int(task['centered']))
            self.assertIn('.tran 2p 40n 0 2p', deck)
            self.assertIn('CLOAD OUT 0 20f', deck)
            self.assertIn('V(XD:Xfine_pre:Xa:', deck)
            self.assertIn('V(XD:Xfine_pre:Xb:', deck)

    def test_fresh_parity_requires_dc_preservation_and_both_voltage_directions(self):
        import numpy as np
        t=np.linspace(0,40e-9,4001)
        knots=[(0.,0.)]
        for k in range(8):
            rise=2.1e-9+k/310e6;fall=rise+.6/310e6
            knots += [(rise-50e-12,0.),(rise+50e-12,1.8),
                      (fall-50e-12,1.8),(fall+50e-12,0.)]
        knots += [(40e-9,0.)]
        v=np.interp(t,*zip(*knots));a=np.column_stack([t,v,v,np.ones_like(t)])
        names=['time','v(in)','v(out)','v(float)']
        result={key:False for key in p.prior.KEYS}
        result.update(current_downstream_250ps_slew_domain_passed=True,
                      terminal_stress=[],controls=[],programming_gates=[])
        rows=[dict(error=None,result=result) for _ in range(5)]
        for drift,reverse,expected in ((0.,.0001,True),(1e-6,.0001,False),(0.,.003,False)):
            b=a.copy();b[:,3]+=drift
            with patch.object(p,'validate',side_effect=[(names,a),(names,b)]), \
                 patch.object(p.prior.numerical,'wave_difference',side_effect=[
                     dict(maximum_all_vector_error_v=.0001),dict(maximum_all_vector_error_v=reverse)]):
                proof=p.parity(p.ROOT/'build/unused-p40n32-parity',rows,4,1)
            self.assertEqual(proof['passed'],expected)
