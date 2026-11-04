# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_dcdl_mim_v2 as evidence

class MIMEvidenceTests(unittest.TestCase):
    def fixture(self,root,stress_passed=True,duplicate=False):
        out=root/'build/diagnostics/digital_dcdl_batch_v2/case';folder=out/'0';folder.mkdir(parents=True)
        task=dict(id='0',spec=dict(process='tt',temperature=25,coarse=0,codes=list(range(32))))
        samples=[dict(code=i,rise_delay_ps=300+8*i,fall_delay_ps=340+7*i) for i in range(32)]
        if duplicate:samples[-1]['code']=30
        result=dict(samples=samples,custom_mos_stress_passed=stress_passed,qualified_phy=False)
        for n in evidence.REQUIRED:(folder/n).write_text('fixture '+n)
        row=dict(task=task,error=None,result=result,files={n:evidence.h.sha(folder/n) for n in evidence.REQUIRED})
        (folder/'summary.json').write_text(json.dumps(row))
        (out/'summary.json').write_text(json.dumps(dict(rows=[row])))
        (out/'manifest.json').write_text(json.dumps(dict(tasks=[task])))
        (out/'state.json').write_text(json.dumps(dict(status='source_screen_complete',cases=1)))
        return out,dict(tasks=[task]),result
    def report(self,out,root,manifest,result):
        with patch.object(evidence,'ROOT',root),patch.object(evidence.dense,'bound',return_value=manifest), \
             patch.object(evidence.dense,'measure',return_value=result),patch.object(evidence.previous,'export_matches_raw'):
            return evidence.report(out)
    def test_dense_samples_keep_source_scope_and_all_stress_failures(self):
        for stress_passed in [True,False]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);out,m,r=self.fixture(root,stress_passed=stress_passed)
                report=self.report(out,root,m,r)
                self.assertFalse(report['qualified_phy'])
                self.assertFalse(report['legal_code_table_admitted'])
                self.assertEqual(report['custom_stress_failures'],int(not stress_passed))
                self.assertTrue(report['groups'][0]['dense_32_codes'])
                self.assertEqual(report['groups'][0]['rise_max_adjacent_step_ps'],8)
    def test_duplicate_code_cannot_form_dense_characterization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,m,r=self.fixture(root,duplicate=True)
            with self.assertRaisesRegex(ValueError,'Duplicate'):self.report(out,root,m,r)
    def test_changed_raw_rejected_before_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,m,r=self.fixture(root)
            (out/'0/bench.raw').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):self.report(out,root,m,r)
