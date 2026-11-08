# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import next_bank_fixture_300_v2 as p
import next_bank_fixture_300 as old
import test_next_bank_fixture_300 as fixtures
from run_native_binary_v2 import translate

class NextBankRunnerTests(unittest.TestCase):
    def test_all_native_loaded_decks_pass_actual_runner_translation(self):
        for original,library,top,identity in fixtures.NextBankFixtureTests().contexts():
            for fine in (0,31):
                deck,obs=p.fixture(original,library,top,identity,next_fine=fine)
                translate(deck)
                line=next(s for s in deck.splitlines() if s.startswith('.print tran '))
                probes=line.split()[2:]
                self.assertEqual(len(probes),len({s.lower().replace(':','.') for s in probes}))
                self.assertEqual(probes.count('V(OUT)'),1);self.assertEqual(probes.count('V(VDD)'),1)
                for d in obs['devices']:
                    for n in d['terminals']:
                        if n!='0':self.assertIn('V('+n+')',probes)
    def test_reproduces_and_preserves_original_preflight_defect(self):
        original,library,top,identity=next(fixtures.NextBankFixtureTests().contexts())
        deck,_=old.fixture(original,library,top,identity)
        with self.assertRaisesRegex(ValueError,'Duplicate native saved vectors'):translate(deck)
    def test_deduplication_preserves_all_original_and_next_observation_names(self):
        original,library,top,identity=next(fixtures.NextBankFixtureTests().contexts())
        raw,old_obs=old.fixture(original,library,top,identity,next_fine=31)
        fixed,new_obs=p.fixture(original,library,top,identity,next_fine=31)
        names=lambda deck:set(next(s for s in deck.splitlines() if s.startswith('.print tran ')).split()[2:])
        self.assertEqual(names(raw),names(fixed));self.assertEqual(old_obs,new_obs)
