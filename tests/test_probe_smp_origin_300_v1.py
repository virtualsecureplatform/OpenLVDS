# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_smp_origin_300_v1 as p


class SMPReferenceTests(unittest.TestCase):
    def test_actual_decks_preserve_models_stimulus_and_native_observations(self):
        out=p.ROOT/'build/unused-smp-reference-test'
        original=(p.PARENT/'0/bench.cir').read_text()
        centered=p.fixture(out,True);unshifted=p.fixture(out,False)
        self.assertEqual(centered.replace(f'.include "{out}/bank.spice"',f'.include "{p.PARENT}/bank.spice"'),original)
        self.assertEqual(centered.replace(p.baseline.admission.SOURCE.numerical_trial.CARD+'\n',''),unshifted)
        self.assertNotIn('I_BENCH_INPUT_CENTER',centered+unshifted)
        for text in (centered,unshifted):
            translated,names=p.runtime.translate(text)
            self.assertNotIn('.options klu',translated)
            self.assertEqual(names,p.runtime.translate(original)[1])

    def test_both_origins_and_all_parity_classifications_required(self):
        rows=[dict(task=dict(id=str(k),centered=k==0),error=None,parity=dict(passed=True)) for k in range(2)]
        self.assertTrue(p.pilot_passed(rows))
        rows[1]['parity']['passed']=False;self.assertFalse(p.pilot_passed(rows))
        rows[1]['parity']=None;rows[1]['error']='native numerical failure';self.assertFalse(p.pilot_passed(rows))
        with self.assertRaisesRegex(ValueError,'both complete'):p.pilot_passed(rows[:1])
