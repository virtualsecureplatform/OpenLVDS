# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import next_bank_tg2_materials_300_v1 as source
import four_bank_fixture_300_v1 as chain


class FourBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m=json.loads((source.PARENT/'manifest.json').read_text());i=m['identity']
        cls.identity=deepcopy(i['source_identity'])
        cls.identity['observations']=i['observations'][source.producer.VARIANT]
        cls.top=i['revisions'][source.producer.VARIANT]['macro_top']
        cls.library=(source.PARENT/source.producer.VARIANT/'bank.spice').read_text()
        cls.original=(source.PARENT/'0/bench.cir').read_text()

    def test_actual_four_sections_and_complete_observations(self):
        deck,obs=chain.fixture(self.original,self.library,self.top,self.identity,codes=((0,0),(1,31),(2,15)))
        self.assertEqual(sum(len(o['devices']) for o in obs.values()),8224)
        names=[d['name'] for o in obs.values() for d in o['devices']]
        self.assertEqual(len(names),len(set(names)))
        self.assertNotIn('CLOAD OUT',deck)
        self.assertEqual(deck.count('CCHAIN_LOAD B3_OUT 0 20f'),1)
        self.assertNotIn('CNEXT_LOAD',deck)
        probes=next(s for s in deck.splitlines() if s.startswith('.print tran ')).split()[2:]
        self.assertEqual(len(probes),len(set(p.lower().replace(':','.') for p in probes)))
        for k,o in enumerate(obs.values()):
            self.assertEqual(len(o['controls']),86);self.assertEqual(len(o['programming_gates']),266)
            for d in o['devices']:
                for node in d['terminals']:
                    if node!='0':self.assertIn('V('+node+')',probes)
            if k:
                self.assertIn('XB'+str(k)+' '+o['input_node']+' '+o['output_node']+' ',deck)
                self.assertEqual(o['input_node'],'OUT' if k==1 else f'B{k-1}_OUT')
        self.assertIn('VB1_E0 B1_E0 0 0',deck)
        self.assertIn('VB2_E0 B2_E0 0 1.8',deck)
        self.assertIn('Xtail_load tap15 unused_tail',self.library)

    def test_reference_pair_and_invalid_reuse(self):
        card=source.producer.numerical_trial.CARD+'\n'
        a,oa=chain.fixture(self.original,self.library,self.top,self.identity)
        b,ob=chain.fixture(self.original.replace(card,''),self.library,self.top,self.identity)
        self.assertEqual(a.replace(card,''),b);self.assertEqual(oa,ob)
        with self.assertRaises(ValueError):chain.fixture(a,self.library,self.top,self.identity)
        with self.assertRaises(ValueError):chain.fixture(self.original,self.library,self.top,self.identity,codes=((0,0),))
