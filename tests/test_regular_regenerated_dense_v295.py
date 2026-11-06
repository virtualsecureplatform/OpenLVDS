# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_regular_regenerated_dense_v295 as p
import probe_regular_regenerated_dense_v294 as dense
import test_regular_regenerated_dense_v294 as fixtures

class RoutedDenseFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.RoutedDenseTests.setUpClass()

    def report(self,rows=None):
        rows=fixtures.RoutedDenseTests.rows if rows is None else rows
        old=[r for r in rows if (r['spec']['coarse'],r['spec']['fine']) in ((0,0),(0,31),(1,0))]
        return dict(rows=[r for r in rows if r not in old],inherited_rows=old,comparison=dense.assess(rows,fixtures.RoutedDenseTests.matrix))

    def write(self,path,report,state=None):
        state=state or dict(status='complete',cases=64,consumed_cases=3,errors=0,qualified_phy=False)
        (path/'state.json').write_text(json.dumps(state));(path/'summary.json').write_text(json.dumps(report));return path

    def test_every_interval_gap_and_overlap_reproduces(self):
        good=self.report()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);p.require_curve(self.write(path,good))
            for field in ('delay_intervals','adjacent_fine_intervals'):
                bad=deepcopy(good);bad['comparison'][field].pop()
                with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))
            bad=deepcopy(good);bad['comparison']['conservative_coarse_overlap_ps']['rise']+=1
            with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))

    def test_characterized_reversal_is_retained_without_legal_table_admission(self):
        rows=deepcopy(fixtures.RoutedDenseTests.rows)
        next(r for r in rows if (r['spec']['coarse'],r['spec']['fine'])==(0,16))['result']['edge_delays_ps']['rise'][0]-=8
        report=self.report(rows)
        self.assertFalse(report['comparison']['raw_adjacent_dense_feasibility_passed'])
        self.assertFalse(report['comparison']['legal_code_table_admitted'])
        with tempfile.TemporaryDirectory() as tmp:p.require_curve(self.write(Path(tmp),report))

    def test_failed_observation_duplicate_code_wrong_condition_or_false_scope_is_rejected(self):
        good=self.report()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for field in ('terminal_stress','programming_gates','controls'):
                bad=deepcopy(good);bad['rows'][0]['result'][field][0]['passed']=False
                with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))
            bad=deepcopy(good);bad['rows'][0]['spec']=bad['rows'][1]['spec']
            with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))
            bad=deepcopy(good);bad['rows'][0]['spec']['duty']=.6
            with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))
            bad=deepcopy(good);bad['comparison']['legal_code_table_admitted']=True
            with self.assertRaisesRegex(ValueError,'cannot admit'):p.require_curve(self.write(path,bad))
            bad=deepcopy(good);bad['rows'].pop()
            with self.assertRaises(ValueError):p.require_curve(self.write(path,bad))

    def test_incomplete_or_wrong_native_transport_context_cannot_advance(self):
        for state in (dict(status='failed'),dict(status='waiting_for_joint_rc'),dict(status='periodic_transport_screen_complete',artifacts={}),
            dict(status='periodic_transport_screen_complete',artifacts=dict(periodic='build/diagnostics/isolated_bank_joint_periodic_v261/0123456789abcdef'))):
            with self.assertRaises(ValueError):p.ready_pilot(state)

if __name__=='__main__':unittest.main()
