# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_lvt_pair_matrix as matrix


class LowThresholdPairMatrix(unittest.TestCase):
    def fixture(self,root):
        children=[]
        for i in range(3):
            folder=root/str(i);folder.mkdir();(folder/'summary.json').write_text('{}')
            children.append(dict(root=str(i),manifest_sha256='expected'))
        return children

    def test_incomplete_pilots_cannot_start_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.fixture(root);(root/'1/summary.json').unlink()
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all three'):matrix.pilot_gate(children,1)
                run.assert_not_called()

    def test_negative_pilot_blocks_advancement_after_actual_remeasurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.fixture(root)
            reports=[dict(diagnostic_complete=True,manifest_sha256='expected',lvt_decision_pair=dict(metrics=dict(passed=p))) for p in [True,False,True]]
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run',side_effect=reports) as run:
                with self.assertRaisesRegex(ValueError,'pilot failed'):matrix.pilot_gate(children,1)
                self.assertEqual(run.call_count,3)

    def test_passing_flags_require_complete_manifest_bound_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=self.fixture(root)
            report=dict(diagnostic_complete=True,manifest_sha256='expected',lvt_decision_pair=dict(metrics=dict(passed=True)))
            with patch.object(matrix,'ROOT',root),patch.object(matrix.diagnosis,'run',return_value=report) as run:
                matrix.pilot_gate(children,1);self.assertEqual(run.call_count,3)
                run.return_value=dict(report,manifest_sha256='different')
                with self.assertRaisesRegex(ValueError,'prove completion'):matrix.pilot_gate(children,1)


if __name__=='__main__':unittest.main()
