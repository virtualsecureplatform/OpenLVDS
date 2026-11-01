# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from receiver_static_matrix import selected_cases


class StaticMatrixCoverage(unittest.TestCase):
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
