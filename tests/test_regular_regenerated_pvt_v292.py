# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_regular_regenerated_pvt_v292 as p
import probe_regular_regenerated_pvt_v291 as matrix
import test_regular_regenerated_pvt_v291 as fixtures

class RoutedPvtFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RoutedPvtTests.setUpClass();rows=fixtures.RoutedPvtTests.rows
        cls.report=dict(rows=rows[27:],inherited_rows=rows[:27],comparison=matrix.assess(rows,fixtures.RoutedPvtTests.matrix))
        cls.state=dict(status='complete',cases=405,consumed_cases=27,errors=0,qualified_phy=False)

    def write(self,path,state,report):
        (path/'state.json').write_text(json.dumps(state));(path/'summary.json').write_text(json.dumps(report));return path

    def test_actual_matrix_handoff_recomputes_all_fifteen_group_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);p.require_matrix(self.write(path,self.state,self.report))
            bad=deepcopy(self.report);bad['comparison']['pvt_points'][0]['conservative_coarse_overlap_ps']['rise']+=1
            with self.assertRaisesRegex(ValueError,'do not reproduce'):p.require_matrix(self.write(path,self.state,bad))

    def test_incomplete_wrong_context_and_failed_transport_never_advance(self):
        for state in [dict(status='waiting_for_joint_rc'),dict(status='failed'),dict(status='periodic_transport_screen_complete',artifacts={}),
            dict(status='periodic_transport_screen_complete',artifacts=dict(periodic='build/diagnostics/isolated_bank_joint_periodic_v261/0123456789abcdef'))]:
            with self.assertRaises(ValueError):p.ready_pilot(state)

    def test_missing_or_duplicate_condition_and_failed_native_observation_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for field in ('rows','inherited_rows'):
                bad=deepcopy(self.report);bad[field].pop()
                with self.assertRaises(ValueError):p.require_matrix(self.write(path,self.state,bad))
            bad=deepcopy(self.report);bad['rows'][0]['spec']=bad['rows'][1]['spec']
            with self.assertRaisesRegex(ValueError,'unique'):p.require_matrix(self.write(path,self.state,bad))
            for field in ('terminal_stress','programming_gates','controls'):
                bad=deepcopy(self.report);bad['rows'][0]['result'][field][0]['passed']=False
                with self.assertRaisesRegex(ValueError,'safety'):p.require_matrix(self.write(path,self.state,bad))
            bad=deepcopy(self.report);bad['rows'][0]['result']['edge_delays_ps']['rise'][0]=float('nan')
            with self.assertRaises(ValueError):p.require_matrix(self.write(path,self.state,bad))

if __name__=='__main__':unittest.main()
