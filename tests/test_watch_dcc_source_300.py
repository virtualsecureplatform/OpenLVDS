# SPDX-License-Identifier: GPL-3.0-only
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import watch_dcc_source_300 as p


class SourceWatchTests(unittest.TestCase):
    def receipt(self,root,original=True,independent=True,status='complete'):
        native=root/'native';folder=native/'0';folder.mkdir(parents=True,exist_ok=True)
        task=dict(id='0',spec=dict(phase_error_ps=0))
        files={}
        for name in p.replay.REQUIRED:
            path=folder/name;path.write_text('fixed witness '+name);files[name]=p.sha(path)
        result=dict(event_integrity_passed=original,pulse_generator_integrity_passed=True,symmetric_timing_passed=True)
        (folder/'summary.json').write_text(json.dumps(dict(task=task,error=None,result=result,files=files)))
        inputs={str(folder/name):digest for name,digest in files.items()}
        inputs[str(folder/'summary.json')]=p.sha(folder/'summary.json')
        identity=dict(version=p.replay.VERSION,parent=str(native),cases=['0'],full_matrix=False,
                      inputs=inputs,example_independent=independent)
        out=root/'receipts'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        out.mkdir(parents=True)
        (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False)))
        (out/'state.json').write_text(json.dumps(dict(status=status,cases=1,qualified_phy=False)))
        row=dict(case='0',original_metrics_reproduced=True,original_source_passed=original,
                 independent=dict(independent_source_screen_passed=independent))
        report=dict(rows=[row],source_only=True,qualified_phy=False,
                    all_selected_source_screens_passed=original and independent,
                    complete_810_source_matrix_admitted=False)
        (out/'summary.json').write_text(json.dumps(report))
        return native,{'0':task},out

    def test_adopts_complete_bound_receipt_without_admitting_a_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root)
            covered,records,partial=p.index_receipts(root/'receipts',str(native),tasks)
            self.assertEqual(set(covered),{'0'});self.assertFalse(partial)
            self.assertEqual(len(records),1)
            self.assertFalse(next(iter(records.values()))['source_admitted'])

    def test_changed_native_witness_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root)
            (native/'0/bench.raw').write_text('changed raw data')
            with self.assertRaisesRegex(ValueError,'input changed'):
                p.index_receipts(root/'receipts',str(native),tasks)

    def test_partial_receipt_is_not_counted_or_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root,status='running')
            covered,_,partial=p.index_receipts(root/'receipts',str(native),tasks)
            self.assertFalse(covered);self.assertEqual(partial,{'0'})
            with self.assertRaisesRegex(ValueError,'Partial replay'):
                p.batch_cases(['0'],partial,False)

    def test_original_failure_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root,original=False)
            covered,_,_=p.index_receipts(root/'receipts',str(native),tasks)
            self.assertFalse(covered['0']['original_source_passed'])

    def test_conflicting_independent_results_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root)
            self.receipt(root,independent=False)
            with self.assertRaisesRegex(ValueError,'Conflicting'):
                p.index_receipts(root/'receipts',str(native),tasks)

    def test_batches_wait_for_complete_cohort_or_terminal_parent(self):
        pending=[str(k) for k in range(234,251)]
        self.assertEqual(p.batch_cases(pending,set(),False),[])
        self.assertEqual(p.batch_cases(pending,set(),True),pending)
        self.assertEqual(len(p.batch_cases(pending+['251','252'],set(),False)),18)

    def test_native_execution_error_is_not_replayable_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native,tasks,_=self.receipt(root)
            path=native/'0/summary.json';row=json.loads(path.read_text())
            row['error']='native execution failure';path.write_text(json.dumps(row))
            done,errors=p.completed_cases(native,tasks)
            self.assertEqual(done,[]);self.assertEqual(errors,['0'])
