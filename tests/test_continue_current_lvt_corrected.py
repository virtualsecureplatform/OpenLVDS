# SPDX-License-Identifier: GPL-3.0-only
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_current_lvt_corrected as resume


class CorrectedChildContinuation(unittest.TestCase):
    def test_control_must_be_preserved_and_retired_before_standalone_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pair = root/'build/diagnostics/current_lvt_link/test'; pair.mkdir(parents=True)
            with patch.object(resume, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'retire the stalled control'):
                    resume.validate(pair)

    def test_retirement_and_child_manifest_bindings_select_only_corrected_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pair = root/'build/diagnostics/current_lvt_link/test'; pair.mkdir(parents=True)
            children = []
            for ratio in [100, 110]:
                child = root/'build/diagnostics/analog_link_pilot'/str(ratio); child.mkdir(parents=True)
                (child/'manifest.json').write_text('{}')
                children.append(dict(current_ratio=ratio, root=str(child.relative_to(root)), manifest_sha256=resume.link.pilot.digest(child/'manifest.json')))
            (pair/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children, inputs={}, source_proofs={}))))
            receipt = root/'build/diagnostics/resident_jobs/stop/after_stop.json'; receipt.parent.mkdir(parents=True)
            after = dict(all_old_processes_gone=True, all_archived_files_unchanged=True,
                         control_electrically_inconclusive=True, paired_comparison_complete=False, unit=dict(MainPID='0'))
            receipt.write_text(json.dumps(after))
            receipt.with_name('before_stop.json').write_text(json.dumps(dict(files={str((pair/'manifest.json').relative_to(root)):resume.link.pilot.digest(pair/'manifest.json')})))
            (pair/'retirement.json').write_text(json.dumps(dict(after, receipt=str(receipt.relative_to(root)))))
            with patch.object(resume, 'ROOT', root):
                self.assertEqual(resume.validate(pair)[0], root/children[1]['root'])
                (root/children[1]['root']/'manifest.json').write_text('{"changed":true}')
                with self.assertRaisesRegex(ValueError, 'child context changed'):
                    resume.validate(pair)

    def test_partial_corrected_child_is_preserved_before_original_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); child = root/'child'; child.mkdir(); raw = child/'bench.raw'; raw.write_bytes(b'partial retained')
            with patch.object(resume, 'validate', return_value=(child, root/'receipt', root/'before')), \
                    patch.object(resume.link.pilot, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial corrected-child output retained'):
                    resume.run(root/'pair')
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'partial retained')

    def test_successful_corrected_child_cannot_complete_or_qualify_the_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); child = root/'child'; child.mkdir(); pair = root/'pair'; pair.mkdir()
            receipt, before = root/'receipt', root/'before'
            for p in [child/'manifest.json', pair/'manifest.json', receipt, before]:
                p.write_text('{}')
            (child/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True, metrics=dict(passed=True, sampling_margin_passed=False))))
            with patch.object(resume, 'ROOT', root), patch.object(resume, 'validate', return_value=(child, receipt, before)), \
                    patch.object(resume.link, 'profile', return_value=nullcontext()), patch.object(resume.link.pilot, 'run'):
                report = resume.run(pair)
            self.assertTrue(report['corrected_child_only'])
            self.assertFalse(report['paired_comparison_complete'])
            self.assertTrue(report['control_electrically_inconclusive'])
            self.assertFalse(report['qualified_phy'])
            self.assertFalse((pair/'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
