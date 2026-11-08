# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_distributed_pair_300_v1 as p


class NativePairRefusalTests(unittest.TestCase):
    def test_pending_reference_refused_before_full_binding_or_receipt(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT/'build') as folder:
            parent=Path(folder)
            (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.tg2.VERSION))))
            with patch.object(p.tg2,'bound') as bound:
                with self.assertRaisesRegex(ValueError,'still pending: 4'):
                    p.run(parent)
                bound.assert_not_called()
            self.assertEqual({n.name for n in parent.iterdir()},{'manifest.json'})

    def test_only_ramped_family_registered(self):
        for producer in (p.medium,p.p40n32,p.tg2):
            with tempfile.TemporaryDirectory(dir=p.ROOT/'build') as folder:
                parent=Path(folder)
                (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=producer.VERSION))))
                self.assertIs(p.select_producer(parent),producer)
        self.assertNotIn(p.distributed.VERSION,p.PRODUCERS)

    def test_different_stimulus_pair_rejected_before_artifact_creation(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT/'build') as folder:
            parent=Path(folder)
            for number in ('4','1'):
                (parent/number).mkdir();(parent/number/'summary.json').write_text('{}')
            tasks=[dict(id=str(k),variant='x',spec=dict(duty=.6),centered=k!=4) for k in range(5)]
            tasks[4]['spec']=dict(duty=.4)
            with patch.object(p,'select_producer',return_value=p.tg2), \
                    patch.object(p.tg2,'bound',return_value=dict(tasks=tasks)):
                with self.assertRaisesRegex(ValueError,'same-stimulus'):
                    p.run(parent)
