# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_release_300 import check, local
from xyce_profile_300 import sha


class Release300(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = Path(__file__).resolve().parents[1]
        for name in ('qualification_300.json', 'clocking_300mhz.json', 'qualification_io_300.json', 'io_300.json'):
            (self.root / name).write_bytes((source / name).read_bytes())
        self.policy = json.loads((self.root / 'qualification_300.json').read_text())

    def test_missing_is_not_qualified(self):
        r = check(self.root)
        self.assertFalse(r['qualified_phy'])
        self.assertTrue(all(x['state'] == 'missing' for x in r['gates']))

    def test_external_evidence_rejected(self):
        with self.assertRaises(ValueError):
            local(self.root, '../outside.json')

    def test_incomplete_and_changed_evidence_rejected(self):
        gate = self.policy['gates'][0]
        receipt = dict(gate=gate, contract_sha256=sha(self.root / 'clocking_300mhz.json'),
                       state='pass', complete=False, files={}, checks={})
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(receipt))
        self.policy['evidence'][gate] = dict(path='receipt.json', sha256=sha(path))
        (self.root / 'qualification_300.json').write_text(json.dumps(self.policy))
        self.assertEqual(check(self.root)['gates'][0]['state'], 'fail')
        path.write_text('{}')
        self.assertIn('hash mismatch', check(self.root)['gates'][0]['error'])

    def test_gate_removal_rejected(self):
        self.policy['gates'].remove('detector_unequal_slew')
        (self.root / 'qualification_300.json').write_text(json.dumps(self.policy))
        with self.assertRaises(ValueError):
            check(self.root)

    def test_io_policy_is_separate_and_unqualified(self):
        # The working policy may carry receipts; without evidence nothing passes.
        policy = json.loads((self.root / 'qualification_io_300.json').read_text())
        policy['evidence'] = {}
        (self.root / 'qualification_io_300.json').write_text(json.dumps(policy))
        r = check(self.root, policy_name='qualification_io_300.json')
        self.assertEqual(len(r['gates']), 12)
        self.assertTrue(all(x['state'] == 'missing' for x in r['gates']))
        self.assertFalse(r['qualified'])
        self.assertEqual({v['macro'] for v in r['views']}, {'openlvds_io_tx', 'openlvds_io_rx'})
        self.assertEqual(r['contract_sha256'], sha(self.root / 'io_300.json'))

    def test_io_pass_never_qualifies_phy(self):
        self.assertFalse(check(self.root, policy_name='qualification_io_300.json')['qualified_phy'])

    def test_io_gate_removal_rejected(self):
        policy = json.loads((self.root / 'qualification_io_300.json').read_text())
        policy['gates'].remove('offset_and_mismatch')
        (self.root / 'qualification_io_300.json').write_text(json.dumps(policy))
        with self.assertRaises(ValueError):
            check(self.root, policy_name='qualification_io_300.json')

    def test_io_contract_without_gates_rejected(self):
        terms = json.loads((self.root / 'io_300.json').read_text())
        terms['release_gates'] = []
        (self.root / 'io_300.json').write_text(json.dumps(terms))
        with self.assertRaises(ValueError):
            check(self.root, policy_name='qualification_io_300.json')

    def test_unknown_policy_rejected(self):
        with self.assertRaises(ValueError):
            check(self.root, policy_name='qualification_other.json')

    def test_io_contract_edge_window_matches_standard(self):
        r = json.loads((self.root / 'io_300.json').read_text())['requirements']
        ui_ps = 1e6 / (max(r['clock_test_mhz']) * r['bits_per_cycle'])
        self.assertEqual(r['tx_transition_20_80_min_ps'], 260)
        self.assertAlmostEqual(r['tx_transition_max_ui_fraction'] * ui_ps, 483.87, places=2)


if __name__ == '__main__':
    unittest.main()
