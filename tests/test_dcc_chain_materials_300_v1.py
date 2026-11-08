# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_materials_300_v1 as p


class CombinedMaterialTests(unittest.TestCase):
    def test_actual_combined_pair_preserves_every_native_map(self):
        manifest=json.loads((p.PARENT/'manifest.json').read_text())
        library=p.fanout.namespace((p.DCC/'cells.spice').read_text()+'\n'+(p.DCC/'hold1.spice').read_text())
        rows=list(p.tasks(p.ROOT/'build/unused-combined-loading-test',manifest,library))
        self.assertEqual([r[0]['centered'] for r in rows],[True,False])
        self.assertEqual(rows[0][1].replace(p.chain.SOURCE.numerical_trial.CARD+'\n',''),rows[1][1])
        self.assertEqual(rows[0][2],rows[1][2])
        for task,deck,obs in rows:
            original=json.loads((p.PARENT/task['id']/'observations.json').read_text())
            self.assertEqual(obs['sections'],original)
            self.assertEqual(sum(len(o['devices']) for o in original.values()),8224)
            self.assertEqual(set(obs['dcc']),{'0','1'})
            self.assertIn('XDC0 IN B1_OUT',deck);self.assertIn('XDC1 OUT B2_OUT',deck)
            names=[d['name'] for o in list(obs['sections'].values())+list(obs['dcc'].values()) for d in o['devices']]
            self.assertEqual(len(names),len(set(names)))
