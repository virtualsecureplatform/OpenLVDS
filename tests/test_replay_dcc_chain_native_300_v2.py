# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_dcc_chain_native_300_v2 as p


class CombinedReplayPreflightTests(unittest.TestCase):
    def test_pending_native_case_refused_without_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.four.VERSION))))
            with patch.object(p.four,'bound',side_effect=AssertionError('must not bind pending trace')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['0'])
                for cases in ([],['0','0'],['2'],['../0']):
                    with self.subTest(cases=cases),self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,cases)

    def test_unregistered_native_producer_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version='unknown'))))
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.run(parent,['0'])


import test_dcc_chain_measure_300_v2 as fixtures


class CombinedReplayBinaryTests(fixtures.CombinedPulseBinaryTests):
    def test_internal_hold_failure_overrides_correct_output_transport(self):
        import shutil
        original=fixtures.p.measure
        def replay_fixture(folder,observations,s):
            expected=original(folder,observations,s)
            # Reuse the complete binary writer and fault mutation, while
            # exercising receipt creation and both real measurement readers.
            root=folder/('valid-replay' if expected['combined_loading_transport_passed'] else 'failed-point-replay')
            parent=root/'producer';case=parent/'0';case.mkdir(parents=True)
            shutil.copyfile(folder/'bench.raw',case/'bench.raw')
            for n in ('bench.cir','bench.ngspice.cir','ngspice.log'):(case/n).write_text('* synthetic replay fixture\n')
            for n in ('bank.spice','dcc.spice'):(parent/n).write_text('* synthetic reader fixture\n')
            p.four.atomic(case/'observations.json',observations)
            task=dict(id='0',centered=True,spec=s)
            manifest=dict(identity=dict(version=p.four.VERSION,inputs={}),tasks=[task])
            p.four.atomic(parent/'manifest.json',manifest)
            row=dict(task=task,error=None,result=expected,files={f.name:p.four.sha(f) for f in case.iterdir()})
            p.four.atomic(case/'summary.json',row)
            # The synthetic producer-binding boundary is the sole substituted
            # validation; actual input hashing and both algorithms are retained.
            with patch.object(p,'ROOT',root),patch.object(p.four,'bound',return_value=manifest),\
                    patch.object(p.four.metrology,'measure',side_effect=original):
                out=p.run(parent,['0'])
                receipt=json.loads((out/'summary.json').read_text())
                self.assertTrue(receipt['all_selected_combined_native_metrics_reproduced'])
                self.assertEqual(receipt['rows'][0]['source_point_passed'],expected['combined_loading_transport_passed'])
                self.assertFalse(receipt['qualified_phy']);self.assertFalse(receipt['whole_bank_admitted'])
                with (case/'bench.raw').open('ab') as handle:handle.write(b'changed')
                with self.assertRaisesRegex(ValueError,'witness changed'):p.run(parent,['0'])
            return expected
        with patch.object(fixtures.p,'measure',side_effect=replay_fixture):
            super().test_internal_hold_failure_overrides_correct_output_transport()
