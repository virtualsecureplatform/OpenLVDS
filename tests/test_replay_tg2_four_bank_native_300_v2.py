# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_tg2_four_bank_native_300_v2 as p


class ReplayPreflightTests(unittest.TestCase):
    def parent(self,folder,version=None):
        (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(version=version or p.four.VERSION))))
        return folder

    def test_pending_case_refused_before_expensive_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=self.parent(Path(tmp))
            with patch.object(p.four,'bound',side_effect=AssertionError('must not bind pending data')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['0'])

    def test_exact_registry_and_unique_explicit_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=self.parent(Path(tmp))
            self.assertIs(p.select(parent),p.four)
            self.parent(parent,p.legacy.VERSION)
            self.assertIs(p.select(parent),p.legacy)
            self.parent(parent,p.four.VERSION)
            for ids in ([],['0','0'],['2'],['../0']):
                with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,ids)
            self.parent(parent,'unregistered-producer')
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.select(parent)


class ReplayBinaryTests(unittest.TestCase):
    def captured(self,root,*,failed=False):
        import test_four_bank_native_measure_300_v1 as fixtures
        parent=root/'synthetic-producer';folder=parent/'0';folder.mkdir(parents=True)
        helper=fixtures.FourSectionMeasureTests()
        obs,s=helper.fixture(folder,delays=(700,700,900 if failed else 700,700))
        task=dict(id='0',centered=True,spec=s)
        manifest=dict(identity=dict(version=p.four.VERSION,spec=s,inputs={}),tasks=[task])
        p.four.atomic(parent/'manifest.json',manifest)
        (parent/'bank.spice').write_text('* synthetic reader fixture, no simulator\n')
        for name in ('bench.cir','bench.ngspice.cir','ngspice.log'):
            (folder/name).write_text('* synthetic reader fixture\n')
        p.four.atomic(folder/'observations.json',obs)
        result=p.four.metrology.measure(folder,obs,s)
        row=dict(task=task,error=None,result=result,files={x.name:p.four.sha(x) for x in folder.iterdir()})
        p.four.atomic(folder/'summary.json',row)
        return parent,manifest

    def test_complete_binary_replay_preserves_physical_failures(self):
        for failed in (False,True):
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);parent,manifest=self.captured(root,failed=failed)
                # Producer binding is tested separately against real captured
                # fixtures. Here only that boundary is substituted; both raw
                # measurement algorithms and all witness hashing run unchanged.
                with patch.object(p,'ROOT',root),patch.object(p.four,'bound',return_value=manifest):
                    out=p.run(parent,['0'])
                summary=json.loads((out/'summary.json').read_text())
                self.assertTrue(summary['all_selected_four_section_native_metrics_reproduced'])
                self.assertEqual(summary['rows'][0]['source_point_passed'],not failed)
                self.assertFalse(summary['whole_bank_admitted']);self.assertFalse(summary['qualified_phy'])
                self.assertTrue(summary['rows'][0]['independent_four_section_metrics_reproduced'])
                self.assertEqual(json.loads((out/'state.json').read_text())['status'],'complete')

    def test_changed_binary_witness_refused_before_remeasurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent,manifest=self.captured(root)
            with (parent/'0/bench.raw').open('ab') as handle:handle.write(b'changed')
            with patch.object(p,'ROOT',root),patch.object(p.four,'bound',return_value=manifest),\
                    patch.object(p.four.metrology,'measure',side_effect=AssertionError('must reject hash first')):
                with self.assertRaisesRegex(ValueError,'witness changed'):p.run(parent,['0'])
