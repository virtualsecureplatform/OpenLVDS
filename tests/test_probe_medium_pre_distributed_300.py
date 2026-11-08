# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_medium_pre_distributed_300 as p


class MediumPrePilotTests(unittest.TestCase):
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

    def test_pending_predecessor_endpoint_refuses_capture(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT / 'build') as folder:
            (Path(folder) / 'manifest.json').write_text('{}')
            with patch.object(p, 'PREVIOUS', Path(folder)), \
                 patch.object(p.predecessor, 'bound', return_value={}):
                with self.assertRaisesRegex(ValueError, 'Predecessor endpoint still pending'):
                    p.evidence()

    def test_all_five_native_fixtures_preserve_observations_and_stimulus(self):
        source = json.loads((p.PARENT / 'manifest.json').read_text())['identity']
        _, obs, revision = p.architecture.transform((p.PARENT / 'bank.spice').read_text(),
                                                   source['observations'])
        identity = dict(source_identity=source, observations={p.VARIANT: obs},
                        revisions={p.VARIANT: revision})
        for task in p.specifications():
            deck = p.fixture(p.ROOT / 'build/unused-medium-pre-pilot-300', identity, task)
            self.assertEqual(deck.count('tanh((time-'), 16)
            self.assertEqual(deck.count(p.prior.numerical.CARD), int(task['centered']))
            self.assertIn('.tran 2p 40n 0 2p', deck)
            self.assertIn('CLOAD OUT 0 20f', deck)
            self.assertIn('V(XD:Xfine_pre:Xa:', deck)
            self.assertNotIn('V(XD:Xfine_pre:Xb:', deck)
