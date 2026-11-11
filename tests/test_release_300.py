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
        for name in ('qualification_300.json', 'clocking_300mhz.json'):
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


if __name__ == '__main__':
    unittest.main()
