# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_input_current_origin_300_v1 as p
import test_two_bank_native_measure_300_v1 as fixtures


class InputCurrentReplayTests(unittest.TestCase):
    def captured(self,root,*,failed=False):
        helper=fixtures.RelativeTransportTests();helper.setUp()
        spec=dict(helper.s,stop_ns=40)
        reference=root/'reference';(reference/'0').mkdir(parents=True)
        parent=root/'candidate';folder=parent/'0';folder.mkdir(parents=True)
        obs=helper.binary_fixture(reference/'0',fine=0)
        helper.binary_fixture(folder,fine=0,supply=1.803 if failed else 1.8)
        old=p.producer.metrology.measure(reference/'0',obs,spec,next_coarse=0,next_fine=0)
        p.producer.atomic(reference/'0/summary.json',dict(result=old))
        result=p.producer.metrology.measure(folder,obs,spec,next_coarse=0,next_fine=0)
        independent=p.producer.independent.measure(folder,obs,spec,next_coarse=0,next_fine=0)
        parity=p.producer.compare(reference/'0',folder,old,result)
        task=dict(id='0',spec=spec)
        manifest=dict(identity=dict(spec=spec,inputs={}),tasks=[task])
        p.producer.atomic(parent/'manifest.json',manifest)
        (parent/'bank.spice').write_text('* synthetic reader fixture\n')
        for name in ('bench.cir','bench.ngspice.cir','ngspice.log'):
            (folder/name).write_text('* synthetic reader fixture\n')
        p.producer.atomic(folder/'observations.json',obs)
        p.producer.atomic(folder/'summary.json',dict(task=task,error=None,result=result,
            independent_result=independent,parity=parity,files={x.name:p.producer.sha(x) for x in folder.iterdir()}))
        p.producer.atomic(parent/'summary.json',dict(error=None,result=result,parity=parity,
            numerical_origin_passed_for_reference_case=parity['passed'],combined_circuit_admitted=False,qualified_phy=False))
        p.producer.atomic(parent/'state.json',dict(status='complete',cases=1,errors=0,qualified_phy=False))
        return reference,parent,manifest

    def test_real_binary_replay_preserves_pass_and_dc_parity_failure(self):
        for failed in (False,True):
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);reference,parent,manifest=self.captured(root,failed=failed)
                with patch.object(p,'ROOT',root),patch.object(p.producer,'PARENT',reference),patch.object(p.producer,'bound',return_value=manifest):
                    out=p.run(parent)
                summary=json.loads((out/'summary.json').read_text())
                self.assertTrue(summary['independent_metrics_reproduced'])
                self.assertEqual(summary['numerical_origin_passed_for_reference_case'],not failed)
                self.assertFalse(summary['combined_circuit_admitted']);self.assertFalse(summary['qualified_phy'])
                self.assertEqual(json.loads((out/'state.json').read_text())['status'],'complete')

    def test_native_witness_change_rejected_before_remeasurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reference,parent,manifest=self.captured(root)
            with (parent/'0/ngspice.log').open('a') as f:f.write('changed\n')
            with patch.object(p.producer,'bound',return_value=manifest):
                with self.assertRaisesRegex(ValueError,'witness changed'):p.run(parent)

    def test_pending_refused_before_expensive_binding(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p.producer,'bound',side_effect=AssertionError('must not bind')):
            with self.assertRaisesRegex(ValueError,'pending'):p.run(Path(tmp))
