# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_dcdl_node_bank_pvt_v2 as proof


class NodeCurveProofTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for start in range(0,32,8):
            rows.append(dict(task=dict(spec=dict(process='ss',temperature=40,coarse=0,pattern='dense_'+str(start))),
                error=None,result=dict(custom_mos_stress_passed=True,samples=[dict(code=c,rise_delay_ps=500+c*10,fall_delay_ps=600+c*10) for c in range(start,start+8)])))
        rows.append(dict(task=dict(spec=dict(process='ss',temperature=40,coarse=0,pattern='bulk')),error=None,
            result=dict(custom_mos_stress_passed=True,samples=[dict(code=0,rise_delay_ps=498,fall_delay_ps=599)])))
        return rows

    def test_repeat_and_history_values_expand_the_observed_interval(self):
        result=proof.curves(self.rows())[0]
        self.assertTrue(result['complete_dense_and_bulk']);self.assertTrue(result['source_device_stress_passed'])
        first=result['points'][0]
        self.assertEqual((first['rise_observed_min_ps'],first['rise_observed_max_ps'],first['observations']),(498,500,2))

    def test_missing_codes_bulk_failure_and_device_stress_are_never_hidden(self):
        rows=self.rows();rows[0]['result']['samples'].pop()
        self.assertFalse(proof.curves(rows)[0]['complete_dense_and_bulk'])
        rows=self.rows();rows[-1].update(error='failed',result=None)
        self.assertFalse(proof.curves(rows)[0]['complete_dense_and_bulk'])
        rows=self.rows();rows[-1]['result']['custom_mos_stress_passed']=False
        self.assertFalse(proof.curves(rows)[0]['source_device_stress_passed'])
