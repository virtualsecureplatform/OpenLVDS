# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_tg2_entry_domain_300_v1 as p
from run_native_binary_v2 import translate


class EntryDomainFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded=json.loads((p.PARENT/'manifest.json').read_text())
        cls.single=json.loads((p.SOURCE_BANK/'manifest.json').read_text())
        cls.library=(p.PARENT/'bank.spice').read_text()
        cls.specs=p.specifications(cls.loaded['identity']['spec'])

    def test_full_actual_native_maps_and_eight_case_pairs_regenerate(self):
        expected=json.loads((p.PARENT/'0/observations.json').read_text())
        for s in self.specs:
            reference=None
            for centered in (False,True):
                deck,obs=p.fixture(p.ROOT/'build/unused-entry-domain',self.single['identity'],self.library,s,centered)
                translate(deck)
                self.assertEqual(obs,expected)
                self.assertEqual(deck.count('V_ENTRY IN 0 PWL('),1)
                self.assertNotIn('BIN IN 0',deck);self.assertNotIn('CLOAD OUT 0',deck)
                self.assertEqual(sum(len(o['devices']) for o in obs.values()),4112)
                if centered:
                    self.assertEqual(deck.replace(p.SOURCE.numerical_trial.CARD+'\n','',1),reference)
                else:reference=deck

    def rows(self):
        return [dict(task=dict(id=str(k),setting=k%4,centered=k<4,spec=self.specs[k%4]),
                     error=None,result=dict(two_bank_zero_pilot_passed=True)) for k in range(8)]

    def test_all_domain_settings_and_fresh_pairs_are_required(self):
        rows=self.rows();pairs={str(k):dict(passed=True) for k in range(4)}
        self.assertTrue(p.pilot_passed(rows,pairs))
        with self.assertRaises(ValueError):p.pilot_passed(rows[:4],pairs)
        with self.assertRaises(ValueError):p.pilot_passed(rows,{'0':dict(passed=True)})
        failed=deepcopy(rows);failed[3]['result']['two_bank_zero_pilot_passed']=False
        self.assertFalse(p.pilot_passed(failed,pairs))
        changed=deepcopy(rows);changed[0]['task']['spec']['duty']=.5
        with self.assertRaises(ValueError):p.pilot_passed(changed,pairs)
