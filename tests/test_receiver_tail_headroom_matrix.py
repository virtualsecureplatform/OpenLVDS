# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from receiver_tail_headroom_matrix import selected_cases
import receiver_tail_headroom_matrix as matrix


class TailHeadroomMatrixCoverage(unittest.TestCase):
    def test_child_failure_leaves_terminal_held_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / 'build/diagnostics/receiver_components/parent'
            child = root / 'build/diagnostics/receiver_tail_headroom_static/child'
            output = root / 'build/diagnostics/receiver_tail_headroom_matrix/matrix'
            for folder in [parent, child, output]:
                folder.mkdir(parents=True)
            case = 'schematic_receiver_tt_25'
            requirements = root / 'requirements.json'
            requirements.write_text(json.dumps(dict(process_corners=['tt'], temperatures_c=[25])))
            (parent / 'manifest.json').write_text(json.dumps(dict(tasks=[dict(
                id=case, view='schematic', test='receiver', process='tt', temperature=25)])))
            (child / 'manifest.json').write_text(json.dumps(dict(identity=dict(
                parent=str(parent.relative_to(root)), case=case))))
            identity = dict(parent=str(parent.relative_to(root)),
                producer_sha256=matrix.diagnosis.digest(Path(matrix.__file__)),
                requirements_sha256=matrix.diagnosis.digest(requirements),
                parent_manifest_sha256=matrix.diagnosis.digest(parent / 'manifest.json'),
                children=[dict(case=case, process='tt', temperature=25, root=str(child.relative_to(root)),
                               manifest_sha256=matrix.diagnosis.digest(child / 'manifest.json'))])
            (output / 'manifest.json').write_text(json.dumps(dict(identity=identity)))
            with patch.object(matrix, 'ROOT', root), patch.object(matrix.diagnosis, 'run',
                    side_effect=ValueError('Fixture verification failed')):
                with self.assertRaisesRegex(ValueError, 'Fixture verification failed'):
                    matrix.run(output)
            state = json.loads((output / 'state.json').read_text())
            self.assertEqual(state['status'], 'held_for_diagnosis')
            self.assertFalse(state['qualified_phy'])
            self.assertEqual(state['completed'], 0)
            self.assertFalse((output / 'summary.json').exists())

    def test_requires_each_process_temperature_once_with_its_original_name(self):
        requirements = dict(process_corners=['tt', 'ss'], temperatures_c=[0, 25, 40])
        tasks = [dict(id=f'schematic_receiver_{p}_{t}', view='schematic', test='receiver',
                      process=p, temperature=t) for p in ['tt', 'ss'] for t in [0, 25, 40]]
        manifest = dict(tasks=tasks)
        self.assertEqual(selected_cases(manifest, requirements), tasks)
        for modified in [tasks[:-1], tasks + [tasks[0]], tasks[:-1] + [tasks[0]]]:
            with self.assertRaisesRegex(ValueError, 'coverage'):
                selected_cases(dict(tasks=modified), requirements)
        changed = copy.deepcopy(tasks)
        changed[0]['id'] = 'schematic_receiver_ss_40'
        with self.assertRaisesRegex(ValueError, 'case name'):
            selected_cases(dict(tasks=changed), requirements)

    def test_native_and_rate_cases_cannot_substitute_for_source_static(self):
        for view, test in [('native', 'receiver'), ('schematic', 'receiver_rate')]:
            with self.subTest(view=view, test=test), self.assertRaisesRegex(ValueError, 'coverage'):
                selected_cases(dict(tasks=[dict(id='other', view=view, test=test, process='tt', temperature=25)]),
                               dict(process_corners=['tt'], temperatures_c=[25]))


if __name__ == '__main__':
    unittest.main()
