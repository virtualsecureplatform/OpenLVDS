# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import p40n32_pre_distributed_bank_300 as p


class P40N32PreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = p.parent.parent.mim.ROOT / 'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'
        cls.original = (folder / 'bank.spice').read_text()
        cls.obs = json.loads((folder / 'manifest.json').read_text())['identity']['observations']

    def test_preserves_capacitors_fine_driver_and_native_observation_coverage(self):
        old, obs, revision = p.parent.transform(self.original, self.obs)
        new, actual, result = p.transform(self.original, self.obs)
        before = p.SOURCE.native.definitions(old)[revision['macro_top']][1]
        after = p.SOURCE.native.definitions(new)[result['macro_top']][1]
        self.assertEqual([(a[0], b[0]) for a, b in zip(before, after) if a != b],
                         [('Xfine_pre', 'Xfine_pre')])
        self.assertEqual(actual['controls'], obs['controls'])
        self.assertEqual(actual['programming_gates'], obs['programming_gates'])
        self.assertEqual((result['native_mos'], result['native_mims']), (2056, 202))
        pre = [d for d in actual['devices'] if d['name'].startswith('XD:Xfine_pre:')]
        self.assertEqual(sum('pfet_' in d['model'] for d in pre), 40)
        self.assertEqual(sum('nfet_' in d['model'] for d in pre), 32)
        self.assertFalse(result['qualified_phy'])

    def test_rejects_changed_source_device_map(self):
        from copy import deepcopy
        broken = deepcopy(self.obs)
        broken['devices'][0]['terminals'][0] = 'unqualified_node'
        with self.assertRaises(ValueError):
            p.transform(self.original, broken)

    def test_native_decks_accept_all_endpoint_observations(self):
        import probe_distributed_fine_300 as pilot
        source = json.loads((pilot.PARENT / 'manifest.json').read_text())['identity']
        _, obs, revision = p.transform(self.original, self.obs)
        identity = dict(source_identity=source, observations={'medium_pre': obs},
                        revisions={'medium_pre': revision})
        for original in pilot.specifications():
            if original['variant'] != 'split_c1_c1':
                continue
            task = dict(original, variant='medium_pre')
            deck = pilot.fixture(pilot.ROOT / 'build/unused-medium-pre-300', identity, task)
            self.assertIn('.tran 2p 40n 0 2p', deck)
            self.assertIn('CLOAD OUT 0 20f', deck)
            self.assertIn('V(XD:Xfine_pre:Xa:', deck)
            self.assertIn('V(XD:Xfine_pre:Xb:', deck)
