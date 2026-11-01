# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_decision_load_matrix as matrix


class DecisionLoadMatrix(unittest.TestCase):
    def fixture(self):
        req=dict(process_corners=['tt','ff','ss','fs','sf'],temperatures_c=[0,25,40])
        cases=[dict(case=f'schematic_receiver_{p}_{t}',process=p,temperature=t,root=f'{p}_{t}',manifest_sha256='m')
               for p in req['process_corners'] for t in req['temperatures_c']]
        return dict(identity=dict(children=cases)),req

    def test_requires_exact_original_pvt_coverage_and_pilots_first(self):
        manifest,req=self.fixture();children=matrix.selected_cases(manifest,req)
        self.assertEqual([(c['process'],c['temperature']) for c in children[:3]],matrix.PILOTS)
        self.assertEqual(len(children),15)
        for cases in [manifest['identity']['children'][:-1],manifest['identity']['children']+[manifest['identity']['children'][0]]]:
            with self.assertRaisesRegex(ValueError,'coverage'):matrix.selected_cases(dict(identity=dict(children=cases)),req)
        altered=copy.deepcopy(manifest);altered['identity']['children'][0]['case']='schematic_receiver_sf_40'
        with self.assertRaisesRegex(ValueError,'case name'):matrix.selected_cases(altered,req)

    def gate_fixture(self,root):
        children=[]
        for i in range(3):
            path=root/str(i);path.mkdir();(path/'summary.json').write_text('{}')
            children.append(dict(root=str(i),manifest_sha256='m'))
        return children

    def test_incomplete_pilot_cannot_launch_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.gate_fixture(root);(root/'2/summary.json').unlink()
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run') as run:
                with self.assertRaisesRegex(ValueError,'Pilot incomplete'):matrix.pilot_gate(root,children,1)
                run.assert_not_called()

    def test_failed_completed_pilot_blocks_remaining_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.gate_fixture(root)
            reports=[dict(manifest_sha256='m',diagnostic_complete=True,stronger_pmos_load=dict(metrics=dict(passed=p))) for p in [True,False,True]]
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run',side_effect=reports) as run:
                with self.assertRaisesRegex(ValueError,'static pilot failed'):matrix.pilot_gate(root,children,1)
                self.assertEqual(run.call_count,3)
                self.assertEqual([c.args[0] for c in run.call_args_list],[root/str(i) for i in range(3)])

    def test_all_passing_pilots_must_be_remeasured_and_manifest_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.gate_fixture(root)
            report=dict(manifest_sha256='m',diagnostic_complete=True,stronger_pmos_load=dict(metrics=dict(passed=True)))
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run',return_value=report) as run:
                matrix.pilot_gate(root,children,1);self.assertEqual(run.call_count,3)
                run.return_value=dict(report,manifest_sha256='other')
                with self.assertRaisesRegex(ValueError,'prove completion'):matrix.pilot_gate(root,children,1)


if __name__=='__main__':unittest.main()
