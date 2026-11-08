# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_tg2_loaded_native_300_v3 as p


class MatchedReplayTests(unittest.TestCase):
    def test_matched_registry_and_pending_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.matched.VERSION))))
            self.assertIs(p.select(parent),p.matched)
            with patch.object(p.matched,'bound',side_effect=AssertionError('must not bind pending data')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['3'])
                for ids in ([],['0','0'],['4'],['7'],['../0']):
                    with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,ids)

    def test_original_producer_registrations_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp)
            for producer in (p.strict,p.early,p.entry):
                (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=producer.VERSION))))
                self.assertIs(p.select(parent),producer)
            (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version='unknown'))))
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.select(parent)


import test_two_bank_entry_measure_300_v2 as fixtures


class MatchedReplayBinaryTests(fixtures.MatchedReferenceReaderTests):
    def test_complete_100ps_binary_agreement_and_changed_source_rejected(self):
        import shutil
        original=fixtures.p.measure
        def replay_fixture(folder,obs,s,**kwargs):
            expected=original(folder,obs,s,**kwargs)
            if kwargs.get('independent_reader'):return expected
            root=folder/('valid-replay' if expected['two_bank_zero_pilot_passed'] else 'failed-source-replay')
            parent=root/'producer';case=parent/'0';case.mkdir(parents=True)
            shutil.copyfile(folder/'bench.raw',case/'bench.raw')
            for n in ('bench.cir','bench.ngspice.cir','ngspice.log'):(case/n).write_text('* synthetic replay fixture\n')
            (parent/'bank.spice').write_text('* synthetic reader fixture\n')
            p.matched.atomic(case/'observations.json',obs)
            task=dict(id='0',centered=True,spec=s,next_coarse=0,next_fine=0)
            manifest=dict(identity=dict(version=p.matched.VERSION,inputs={},spec='must use task specification'),tasks=[task])
            p.matched.atomic(parent/'manifest.json',manifest)
            p.matched.atomic(case/'summary.json',dict(task=task,error=None,result=expected,
                files={f.name:p.matched.sha(f) for f in case.iterdir()}))
            with patch.object(p,'ROOT',root),patch.object(p.matched,'bound',return_value=manifest),\
                    patch.object(p.matched.metrology,'measure',side_effect=original):
                out=p.run(parent,['0']);receipt=json.loads((out/'summary.json').read_text())
                self.assertTrue(receipt['all_selected_loaded_native_metrics_reproduced'])
                self.assertEqual(receipt['rows'][0]['source_point_passed'],expected['two_bank_zero_pilot_passed'])
                self.assertFalse(receipt['whole_bank_admitted']);self.assertFalse(receipt['qualified_phy'])
                with (case/'bench.raw').open('ab') as handle:handle.write(b'changed')
                with self.assertRaisesRegex(ValueError,'witness changed'):p.run(parent,['0'])
            return expected
        with patch.object(fixtures.p,'measure',side_effect=replay_fixture):
            super().test_complete_100ps_binary_agreement_and_changed_source_rejected()
