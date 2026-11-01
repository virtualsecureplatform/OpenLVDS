# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_architecture_matrix as matrix


class ArchitectureMatrixAdmission(unittest.TestCase):
    def fixture(self, root):
        (root/'scripts').mkdir(); (root/'scripts/spice_dispatch.py').write_text('captured policy')
        (root/'requirements.json').write_text('{}'); (root/'parent').mkdir()
        (root/'parent/manifest.json').write_text('{}')
        children = []
        for i in range(15):
            child = root/'children'/str(i); child.mkdir(parents=True)
            (child/'manifest.json').write_text(json.dumps(dict(identity=dict(parent='control/'+str(i), architecture_variant='pmos_p8_t4'))))
            (child/'summary.json').write_text('{}')
            children.append(dict(root='children/'+str(i), case=str(i), control='control/'+str(i), manifest_sha256=matrix.sha(child/'manifest.json')))
        folder = root/'build/diagnostics/receiver_architecture_matrix/test'; folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(parent='parent', variant='pmos_p8_t4', inputs={}, code={}, children=children))))
        cases = [dict(case=c['case'], root=c['control']) for c in children]
        return folder, children, cases

    def test_failed_pilot_stops_before_any_later_corner_and_restores_resource_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder, children, cases = self.fixture(root)
            report = dict(diagnostic_complete=True, manifest_sha256=children[0]['manifest_sha256'],
                architecture=dict(metrics=dict(passed=False), observations=dict(observed_thin_guard_passed=True)))
            original = matrix.observed.experiment.lease
            with patch.object(matrix, 'ROOT', root), patch.object(matrix, 'selected_cases', return_value=cases), patch.object(matrix.observed, 'run', return_value=report) as run:
                with self.assertRaisesRegex(ValueError, 'pilot failed'):
                    matrix.run(folder)
                self.assertEqual(run.call_count, 1)
            self.assertIs(matrix.observed.experiment.lease, original)
            self.assertFalse((folder/'summary.json').exists())

    def test_complete_flag_without_matching_child_manifest_cannot_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder, children, cases = self.fixture(root)
            with patch.object(matrix, 'ROOT', root), patch.object(matrix, 'selected_cases', return_value=cases), patch.object(matrix.observed, 'run', return_value=dict(diagnostic_complete=True, manifest_sha256='different')) as run:
                with self.assertRaisesRegex(ValueError, 'incomplete'):
                    matrix.run(folder)
                self.assertEqual(run.call_count, 1)
            self.assertFalse((folder/'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
