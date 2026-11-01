# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_receiver_restore_threshold_physical as handoff


class RestoreThresholdPhysicalHandoff(unittest.TestCase):
    def fixture(self, root):
        matrix = root/'build/diagnostics/receiver_restore_threshold_matrix/test'
        clock = root/'build/diagnostics/receiver_clamp/test'; clock.mkdir(parents=True)
        (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(first_restorer_variant='restore_lvt_n8',
            static_screen=str(matrix.relative_to(root))))))
        (clock/'summary.json').write_text('{}')
        admission = dict(source_clock_passed=True, manifest_sha256=handoff.sha(clock/'manifest.json'),
            report_sha256=handoff.sha(clock/'summary.json'))
        (clock/'source_clock_admission.json').write_text(json.dumps(admission))
        result = dict(root=str(clock.relative_to(root)), variant='restore_lvt_n8', returncode=0,
            admission=admission, admission_sha256=handoff.sha(clock/'source_clock_admission.json'))
        return matrix, clock, result

    def test_exact_clock_receipt_is_required_and_failure_cannot_admit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)):
            root = Path(tmp); matrix, clock, result = self.fixture(root)
            self.assertEqual(handoff.admitted_clock(matrix, 'restore_lvt_n8', result), clock.relative_to(root))
            self.assertIsNone(handoff.admitted_clock(matrix, 'restore_lvt_n8', dict(result, returncode=1)))
            (clock/'summary.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'evidence differs'):
                handoff.admitted_clock(matrix, 'restore_lvt_n8', result)

    def test_other_variant_and_path_escape_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)):
            matrix, clock, result = self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, 'variant binding'):
                handoff.admitted_clock(matrix, 'restore_lvt_n4', result)
            for path in ['/tmp/elsewhere', 'build/diagnostics/receiver_clamp/../../escape']:
                with self.assertRaisesRegex(ValueError, 'result path'):
                    handoff.admitted_clock(matrix, 'restore_lvt_n8', dict(result, root=path))

    def test_native_success_and_failure_never_admit_phy(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)):
            root = Path(tmp); out = root/'native'; out.mkdir()
            (out/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id='captured'), dict(id='sharp_control')])))
            for passed in [False, True]:
                (out/'summary.json').write_text(json.dumps(dict(manifest_sha256=handoff.sha(out/'manifest.json'),
                    diagnostic_complete=True, native_clock_passed=passed)))
                result = handoff.native_result(out)
                self.assertEqual(result['native_clock_passed'], passed)
                self.assertFalse(result['qualified_phy'])

    def test_prior_execution_state_is_retained_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)), patch.object(handoff.subprocess, 'run') as launch:
            out = Path(tmp)/'build/diagnostics/receiver_physical_followup/old'; out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(files={})))
            state = out/'state.json'; state.write_bytes(b'original partial state')
            with self.assertRaisesRegex(ValueError, 'Prior physical followup retained'):
                handoff.run(out)
            self.assertEqual(state.read_bytes(), b'original partial state')
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
