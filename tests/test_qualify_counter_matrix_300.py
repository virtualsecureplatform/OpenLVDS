# SPDX-License-Identifier: GPL-3.0-only
"""Coverage-schema tests only. They never produce an electrical certificate."""
import sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_counter_matrix_300 as p

class CounterMatrixCoverageTests(unittest.TestCase):
    def records(self):
        tasks={str(k):dict(id=str(k),spec=s,mode='simulate') for k,s in enumerate(p.producer.specifications())}
        rows={n:dict(task=deepcopy(t),original_metrics_reproduced=True,only_clear_settling_predicate_changed=True,
            result=dict(stopped_clock_clear_settling_ps=3000,stopped_clock_clear_start_ps=31000,
                        protocol_stop_ns=40,counter_shared_wire_rc_qualified=True)) for n,t in tasks.items()}
        return rows,tasks
    def test_exact_coverage_schema(self):
        rows,tasks=self.records();self.assertEqual(len(p.coverage(rows,tasks)),270)
    def test_missing_or_legacy_frequency_cannot_admit_matrix(self):
        rows,tasks=self.records();rows.pop('269')
        with self.assertRaises(ValueError):p.coverage(rows,tasks)
        rows,tasks=self.records();tasks['0']['spec']['mhz']=410;rows['0']['task']['spec']['mhz']=410
        with self.assertRaises(ValueError):p.coverage(rows,tasks)
    def test_cannot_change_window_or_native_provenance(self):
        for key,value in (('stopped_clock_clear_settling_ps',5000),('protocol_stop_ns',26),('counter_shared_wire_rc_qualified',False)):
            rows,tasks=self.records();rows['0']['result'][key]=value
            with self.assertRaises(ValueError):p.coverage(rows,tasks)
    def test_missing_native_replay_cannot_be_replaced_by_metadata(self):
        rows,tasks=self.records();rows['0']['original_metrics_reproduced']=False
        with self.assertRaises(ValueError):p.coverage(rows,tasks)
