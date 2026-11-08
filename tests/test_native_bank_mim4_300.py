# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_bank_mim4_300_v1 as p
import mim4_evidence_300 as e

class Mim4PilotTests(unittest.TestCase):
    def results(self):
        rows={k:json.loads((e.BASE/str(k)/'summary.json').read_text())['result'] for k in (1,2,3,4)}
        pair=[json.loads((e.SINGLE/str(k)/'summary.json').read_text())['result'] for k in (0,1)]
        return [rows[2],rows[1],rows[3],rows[4],pair]
    def test_actual_fresh_failures_select_p80_mim4(self):
        decision=e.decision(*self.results())
        self.assertEqual(decision['selected_variant'],'p80_c4')
        self.assertAlmostEqual(decision['conservative_baseline_overlap_ps']['rise'],-125.4756762217412)
        self.assertFalse(decision['qualified_phy'])
    def test_no_trial_without_passing_baseline_or_observed_need(self):
        args=self.results();args[0]=deepcopy(args[0]);args[0]['zero_code_quarter_passed']=False
        with self.assertRaises(ValueError):e.decision(*args)
        args=self.results();args[3]=deepcopy(args[3]);args[3]['edge_delays_ps']={k:[1.]*8 for k in ('rise','fall')}
        with self.assertRaises(ValueError):e.decision(*args)
        args=self.results();args[4]=deepcopy(args[4]);args[4][0]['repeated_delay_span_ps']['rise']=19
        with self.assertRaises(ValueError):e.decision(*args)
    def test_missing_receipts_cannot_prepare_science(self):
        with self.assertRaises(ValueError):p.prepare('restored',[])
    def test_complete_mim_native_fixture_and_fixed_protocol(self):
        original=json.loads((p.PARENTS['restored'][1]/'manifest.json').read_text())['identity']
        original['observations']=json.loads((p.BUNDLE/'p80_c4/observations.json').read_text())
        identity=dict(kind='restored',source_identity=original,macro_top=p.TOP)
        for spec,centered in p.specifications('restored'):
            self.assertEqual((spec['fine_copies'],spec['frequency_mhz'],spec['stop_ns']),(4,310,40))
            text=p.fixture(p.ROOT/'build/unused-mim4-300',identity,spec,centered)
            self.assertEqual(text.count('tanh((time-'),16)
            self.assertIn('.tran 2p 40n 0 2p',text)
            self.assertEqual(text.count(p.numerical.CARD),int(centered))
            self.assertIn('V(XD:Xfine_mim30_c3:EN.t0)',text)
            self.assertEqual(text.count(p.TOP),1)
