# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_distributed_parity_300 as replay


class PairSelectionTests(unittest.TestCase):
    def manifest(self):
        return dict(tasks=[dict(id=str(k),**task) for k,task in enumerate(replay.producer.specifications())])

    def test_same_variant_complete_unshifted_centered_pair(self):
        m=self.manifest()
        for v in replay.producer.architecture.VARIANTS:
            tasks=replay.pair_tasks(m,v)
            self.assertEqual([t['centered'] for t in tasks],[False,True])
            self.assertEqual(tasks[0]['spec'],tasks[1]['spec'])

    def test_wrong_stimulus_or_circuit_rejected(self):
        m=self.manifest();v=next(iter(replay.producer.architecture.VARIANTS))
        changed=deepcopy(m);changed['tasks'][1]['spec']['duty']=.4
        with self.assertRaises(ValueError):replay.pair_tasks(changed,v)
        changed=deepcopy(m);changed['tasks'][1]['variant']='another_circuit'
        with self.assertRaises(ValueError):replay.pair_tasks(changed,v)

    def test_missing_unshifted_or_incomplete_pair_rejected(self):
        m=self.manifest();v=next(iter(replay.producer.architecture.VARIANTS))
        changed=deepcopy(m);changed['tasks'][0]['centered']=True
        with self.assertRaises(ValueError):replay.pair_tasks(changed,v)
        with self.assertRaises(ValueError):replay.pair_tasks(dict(tasks=m['tasks'][:1]),v)
        with self.assertRaises(ValueError):replay.pair_tasks(m,'unknown')


if __name__=='__main__':unittest.main()
