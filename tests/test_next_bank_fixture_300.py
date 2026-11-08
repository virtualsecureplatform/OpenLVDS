# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import next_bank_fixture_300 as p
ROOT=Path(__file__).resolve().parents[1]

class NextBankFixtureTests(unittest.TestCase):
    def contexts(self):
        for name in ('native_bank_300_v1/b3f726547e6143f8','native_bank_300_v2/2d31edbabe113146',
                     'native_bank_mim4_300_v1/a8105c49e52731af'):
            folder=ROOT/'build/diagnostics'/name;i=json.loads((folder/'manifest.json').read_text())['identity']
            yield (folder/'2/bench.cir').read_text(),(folder/'bank.spice').read_text(),i['macro_top'],i['source_identity']
    def test_all_three_actual_circuits_retain_complete_next_bank_and_observations(self):
        for original,library,top,i in self.contexts():
            for code in (0,31):
                with self.subTest(top=top,next_fine=code):
                    text,obs=p.fixture(original,library,top,i,next_fine=code)
                    self.assertNotIn('CLOAD OUT 0',text)
                    self.assertIn('XL OUT NEXT_OUT NEXT_S0 NEXT_S1',text)
                    self.assertIn('CNEXT_LOAD NEXT_OUT 0 20f',text)
                    self.assertEqual(len(obs['devices']),len(i['observations']['devices']))
                    self.assertEqual(len(obs['programming_gates']),len(i['observations']['programming_gates']))
                    self.assertEqual(len(obs['controls']),86)
                    self.assertIn('VNEXT_E0 NEXT_E0 0 '+('1.8' if code else '0'),text)
                    for d in obs['devices']:
                        for n in d['terminals']:
                            if n!='0':self.assertIn('V('+n+')',text)
                    for g in obs['programming_gates']:self.assertIn('V('+g['gate_node']+')',text)
                    self.assertFalse(obs['qualified_phy'])
                    self.assertTrue(obs['full_next_bank_native_input_load'])
                    self.assertEqual(text.count('I_BENCH_CURRENT_CENTER'),original.count('I_BENCH_CURRENT_CENTER'))
    def test_cannot_double_load_or_leave_an_original_fixed_capacitor(self):
        original,library,top,i=next(self.contexts())
        changed,_=p.fixture(original,library,top,i)
        with self.assertRaises(ValueError):p.fixture(changed,library,top,i)
        with self.assertRaises(ValueError):p.fixture(original.replace('CLOAD OUT 0 20f','CLOAD OUT 0 30f'),library,top,i)
    def test_rejects_corrupted_first_bank_terminal_or_port_map(self):
        original,library,top,i=next(self.contexts());i=deepcopy(i);i['observations']['devices'][0]['terminals'][0]='CHANGED'
        with self.assertRaises(ValueError):p.fixture(original,library,top,i)
        i['ports']=i['ports'][::-1]
        with self.assertRaises(ValueError):p.fixture(original,library,top,i)
    def test_next_code_must_be_legal(self):
        original,library,top,i=next(self.contexts())
        with self.assertRaises(ValueError):p.fixture(original,library,top,i,next_coarse=16)
        with self.assertRaises(ValueError):p.fixture(original,library,top,i,next_fine=32)
