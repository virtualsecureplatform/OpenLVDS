# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import next_bank_tg2_materials_300_v1 as p
from run_native_binary_v2 import translate


class ActualLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((p.PARENT/'manifest.json').read_text())
        cls.tasks=p.material_tasks(p.PARENT,p.ROOT/'build/unused-tg2-next-load-test',cls.m)

    def test_actual_second_bank_and_all_terminal_probes(self):
        for task in self.tasks:
            deck=task['deck'];translate(deck)
            obs=task['observations'];first=obs['first'];loaded=obs['next']
            self.assertNotIn('CLOAD OUT 0',deck)
            self.assertEqual(deck.count('CNEXT_LOAD NEXT_OUT 0 20f'),1)
            self.assertEqual(len(loaded['devices']),2056)
            self.assertEqual(task['total_native_mos'],4112)
            self.assertEqual(len(loaded['controls']),86)
            self.assertEqual(len(loaded['programming_gates']),266)
            self.assertTrue({d['name'] for d in first['devices']}.isdisjoint(
                            {d['name'] for d in loaded['devices']}))
            probes=next(s for s in deck.splitlines() if s.startswith('.print tran ')).split()[2:]
            self.assertEqual(len(probes),len({s.lower().replace(':','.') for s in probes}))
            for observations in (first,loaded):
                for device in observations['devices']:
                    for node in device['terminals']:
                        if node!='0':self.assertIn('V('+node+')',probes)
            self.assertEqual(probes.count('V(OUT)'),1)
            self.assertEqual(probes.count('V(VDD)'),1)

    def test_each_loaded_code_has_fresh_dc_zero_current_pair(self):
        card=p.producer.numerical_trial.CARD+'\n'
        for a,b in ((0,1),(2,3)):
            unshifted,centered=self.tasks[a],self.tasks[b]
            self.assertEqual(unshifted['next_fine'],centered['next_fine'])
            self.assertNotIn('I_BENCH_CURRENT_CENTER',unshifted['deck'])
            self.assertEqual(centered['deck'].count(card),1)
            self.assertEqual(centered['deck'].replace(card,'',1),unshifted['deck'])
            self.assertEqual(centered['observations'],unshifted['observations'])

    def test_native_next_controls_are_independent_from_first_controls(self):
        a,b=self.tasks[0],self.tasks[2]
        self.assertEqual(a['observations']['first'],b['observations']['first'])
        for task in (a,b):
            for k in range(31):
                self.assertIn(f'VE{k} E{k} 0 0',task['deck'])
                value='0' if task['next_fine']==0 else '1.8'
                self.assertIn(f'VNEXT_E{k} NEXT_E{k} 0 {value}',task['deck'])
            devices={d['name']:d for d in task['observations']['next']['devices']}
            for gate in task['observations']['next']['programming_gates']:
                self.assertEqual(devices[gate['device']]['terminals'][1],gate['gate_node'])

    def test_existing_loaded_deck_cannot_be_loaded_again(self):
        i=deepcopy(self.m['identity']['source_identity'])
        i['observations']=self.m['identity']['observations'][p.producer.VARIANT]
        top=self.m['identity']['revisions'][p.producer.VARIANT]['macro_top']
        library=(p.PARENT/p.producer.VARIANT/'bank.spice').read_text()
        with self.assertRaisesRegex(ValueError,'untouched fresh'):
            p.fixture_tools.fixture(self.tasks[0]['deck'],library,top,i)
