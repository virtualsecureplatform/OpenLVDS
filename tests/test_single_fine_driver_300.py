# SPDX-License-Identifier: GPL-3.0-only
import json, sys, unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import single_fine_driver_300 as p

class SingleDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=p.parent.ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'
        cls.text=(folder/'bank.spice').read_text()
        cls.observations=json.loads((folder/'manifest.json').read_text())['identity']['observations']
    def test_exact_single_intervention_and_complete_native_maps(self):
        text, obs=p.transform(self.text, self.observations)
        self.assertEqual(len(obs['devices']),2070)
        self.assertEqual(obs['controls'],self.observations['controls'])
        self.assertEqual(obs['programming_gates'],self.observations['programming_gates'])
        self.assertEqual(p.SOURCE.native.definitions(text)[p.parent.FINE][1],
                         [['Xa','A','Y','VGND','VPWR',p.parent.recovery.PULLUP]])
        self.assertEqual(p.SOURCE.native.definitions(text)[p.TOP],
                         p.SOURCE.native.definitions(self.text)[p.parent.TOP])
    def test_rejects_already_modified_driver(self):
        text,_=p.transform(self.text,self.observations)
        with self.assertRaises((ValueError,KeyError)):
            p.transform(text.replace(p.TOP,p.parent.TOP),self.observations)
    def test_rejects_missing_or_corrupted_native_observations(self):
        obs=deepcopy(self.observations);obs['devices'].pop()
        with self.assertRaises(ValueError):p.transform(self.text,obs)
        obs=deepcopy(self.observations);obs['devices'][0]['terminals'][0]='CORRUPT'
        with self.assertRaises(ValueError):p.transform(self.text,obs)
