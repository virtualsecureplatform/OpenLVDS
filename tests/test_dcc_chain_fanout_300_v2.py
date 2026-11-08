# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_fanout_300_v2 as p
import dcc_chain_materials_300_v2 as materials
import dcc_chain_measure_300_v2 as reader
from run_native_binary_v2 import translate


class CombinedObservationContractTests(unittest.TestCase):
    def test_full_reader_stack_requests_are_saved_without_circuit_changes(self):
        parent=materials.PARENT;dcc=materials.DCC
        original=(parent/'0/bench.cir').read_text();bank=(parent/'bank.spice').read_text()
        library=p.namespace((dcc/'cells.spice').read_text()+'\n'+(dcc/'hold1.spice').read_text())
        old,old_obs=p.previous.fixture(original,bank,library,'unused-dcc.spice')
        new,obs=p.fixture(original,bank,library,'unused-dcc.spice')
        self.assertEqual(obs,old_obs)
        self.assertEqual([l for l in old.splitlines() if not l.startswith('.print tran ')],
                         [l for l in new.splitlines() if not l.startswith('.print tran ')])
        _,saved=translate(new);_,old_saved=translate(old);required=set()
        def collect(path,names,stop):
            required.update(names);raise RuntimeError('reader requirements captured')
        sections=json.loads((parent/'0/observations.json').read_text())
        manifest=json.loads((parent/'manifest.json').read_text());spec=manifest['identity']['spec']
        with patch.object(reader.previous.chain,'validate',side_effect=collect):
            with self.assertRaisesRegex(RuntimeError,'requirements captured'):
                reader.previous.chain.measure(Path('unused'),sections,spec)
        observations=dict(sections=sections,dcc=obs)
        with patch.object(reader.previous.chain,'measure',return_value={}),patch.object(reader.previous,'validate',side_effect=collect):
            with self.assertRaisesRegex(RuntimeError,'requirements captured'):
                reader.previous.measure(Path('unused'),observations,spec)
        with patch.object(reader.previous,'measure',return_value={}),patch.object(reader,'validate',side_effect=collect):
            with self.assertRaisesRegex(RuntimeError,'requirements captured'):
                reader.measure(Path('unused'),observations,spec)
        self.assertTrue(required<=set(saved),sorted(required-set(saved)))
        self.assertEqual(required-set(old_saved),{'v(b3_out)'})
        self.assertEqual(set(saved)-set(old_saved),{'v(b3_out)'})
