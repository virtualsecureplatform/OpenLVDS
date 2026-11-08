# SPDX-License-Identifier: GPL-3.0-only
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import watch_counter_clear_300 as p

class CounterWatchTests(unittest.TestCase):
    def receipt(self,root,task,status='complete',passed=True):
        i=dict(version='original-three-ns-counter-clear-replay-300-v1',parent='native',cases=[task['id']],
               clear_settling_ps=3000,original_results_preserved=True,example=passed)
        folder=root/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps(dict(identity=i)))
        (folder/'state.json').write_text(json.dumps(dict(status=status,cases=1)))
        row=dict(task=task,original_metrics_reproduced=True,only_clear_settling_predicate_changed=True,
                 original_three_ns_point_passed=passed)
        (folder/'summary.json').write_text(json.dumps(dict(all_selected_original_metrics_reproduced=True,
            qualified_phy=False,all_270_counter_boundaries_present=False,rows=[row])))
        return folder
    def test_indexes_completed_receipts_without_admitting_a_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=dict(id='2',spec={});self.receipt(root,task)
            covered,records,partial=p.index_receipts(root,'native',{'2':task})
            self.assertEqual(set(covered),{'2'});self.assertEqual(len(records),1);self.assertFalse(partial)
    def test_partial_receipts_are_not_counted_or_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=dict(id='2',spec={});self.receipt(root,task,status='running')
            covered,_,partial=p.index_receipts(root,'native',{'2':task})
            self.assertFalse(covered);self.assertEqual(partial,{'2'})
    def test_real_failed_points_remain_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=dict(id='2',spec={});self.receipt(root,task,passed=False)
            covered,_,_=p.index_receipts(root,'native',{'2':task})
            self.assertFalse(covered['2']['original_three_ns_point_passed'])
    def test_conflicting_repeated_case_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=dict(id='2',spec={});self.receipt(root,task,passed=False);self.receipt(root,task,passed=True)
            with self.assertRaises(ValueError):p.index_receipts(root,'native',{'2':task})
    def test_native_error_is_not_treated_as_completed_replay_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=dict(id='2',spec={});folder=root/'2';folder.mkdir()
            (folder/'summary.json').write_text(json.dumps(dict(task=task,error='native failure')))
            done,errors=p.completed_cases(root,{'2':task});self.assertEqual(done,[]);self.assertEqual(errors,['2'])
