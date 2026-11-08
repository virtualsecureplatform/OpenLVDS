# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_distributed_fine_300 as p

class DistributedPilotTests(unittest.TestCase):
    def test_fourteen_cases_include_fresh_pairs_and_full_candidate_endpoints(self):
        tasks=p.specifications();self.assertEqual(len(tasks),14)
        for k,variant in enumerate(p.architecture.VARIANTS):
            self.assertEqual([tasks[j]['variant'] for j in (2*k,2*k+1)],[variant,variant])
            self.assertEqual([tasks[j]['centered'] for j in (2*k,2*k+1)],[False,True])
        self.assertEqual([(t['spec']['coarse'],t['spec']['fine'],t['spec']['duty']) for t in tasks[8:]],[(0,0,.5),(0,31,.4),(1,0,.5)]*2)
        for t in tasks:self.assertEqual((t['spec']['frequency_mhz'],t['spec']['stop_ns'],t['spec']['cycles']),(310,40,8))
    def test_actual_native_fixtures_pass_runner_and_keep_all_controls(self):
        source=json.loads((p.PARENT/'manifest.json').read_text())['identity'];library=(p.PARENT/'bank.spice').read_text()
        models={v:p.architecture.transform(library,source['observations'],v) for v in p.architecture.VARIANTS}
        identity=dict(source_identity=source,observations={v:d[1] for v,d in models.items()},revisions={v:d[2] for v,d in models.items()})
        for task in p.specifications():
            deck=p.fixture(p.ROOT/'build/unused-distributed-fine-300',identity,task)
            self.assertEqual(deck.count('tanh((time-'),16)
            self.assertIn('.tran 2p 40n 0 2p',deck)
            self.assertEqual(deck.count(p.prior.numerical.CARD),int(task['centered']))
            self.assertIn('V(XD:Xfine_pre:Xa:',deck)
            self.assertIn('CLOAD OUT 0 20f',deck)
