# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_receiver_tia_restore as handoff


class FeedbackInverterPhysicalHandoff(unittest.TestCase):
    def fixture(self, root):
        matrix = root/'build/diagnostics/receiver_tia_matrix/test'
        clock = root/'build/diagnostics/receiver_clamp/test'; clock.mkdir(parents=True)
        (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(tia_restore_variant='tia_r4',
            static_screen=str(matrix.relative_to(root))))))
        (clock/'summary.json').write_text('{}')
        admission = dict(source_clock_passed=True, manifest_sha256=handoff.sha(clock/'manifest.json'),
            report_sha256=handoff.sha(clock/'summary.json'))
        (clock/'source_clock_admission.json').write_text(json.dumps(admission))
        result = dict(root=str(clock.relative_to(root)), variant='tia_r4', returncode=0,
            admission=admission, admission_sha256=handoff.sha(clock/'source_clock_admission.json'))
        return matrix, clock, result

    def test_exact_clock_receipt_is_required_and_failure_cannot_admit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)):
            root = Path(tmp); matrix, clock, result = self.fixture(root)
            self.assertEqual(handoff.admitted_clock(matrix, 'tia_r4', result), clock.relative_to(root))
            self.assertIsNone(handoff.admitted_clock(matrix, 'tia_r4', dict(result, returncode=1)))
            (clock/'summary.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'evidence differs'):
                handoff.admitted_clock(matrix, 'tia_r4', result)

    def test_other_variant_and_path_escape_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(handoff, 'ROOT', Path(tmp)):
            matrix, clock, result = self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, 'variant binding'):
                handoff.admitted_clock(matrix, 'tia_r2', result)
            for path in ['/tmp/elsewhere', 'build/diagnostics/receiver_clamp/../../escape']:
                with self.assertRaisesRegex(ValueError, 'result path'):
                    handoff.admitted_clock(matrix, 'tia_r4', dict(result, root=path))

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


    def test_both_variant_workers_can_advance_without_waiting_for_each_other(self):
        barrier = threading.Barrier(2)
        def worker(variant):
            barrier.wait(timeout=2)
            return dict(variant=variant, native_clock_passed=variant=='tia_r4')
        results = handoff.dispatch(handoff.VARIANTS, worker)
        self.assertEqual([r['variant'] for r in results], handoff.VARIANTS)
        self.assertFalse(results[0]['native_clock_passed'])
        self.assertTrue(results[1]['native_clock_passed'])

    def test_duplicate_or_unknown_variants_cannot_dispatch(self):
        for variants in [[], ['tia_r2','tia_r2'], ['unknown']]:
            with patch.object(handoff.subprocess, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'at most once'):
                    handoff.dispatch(variants, lambda v: launch(v))
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
