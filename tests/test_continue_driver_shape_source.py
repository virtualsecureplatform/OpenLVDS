# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_driver_shape_source as followup


class SourcePvtResourceHandoff(unittest.TestCase):
    def test_exact_owner_or_bound_terminal_evidence_required(self):
        relative='build/diagnostics/driver_output_shape/test'
        followup.admissible_owner(dict(MainPID='42',ActiveState='active',ExecStart='scripts/probe_driver_output_shape.py run '+relative),relative,False)
        followup.admissible_owner(dict(MainPID='0',ActiveState='inactive'),relative,True)
        for live,terminal in [(dict(MainPID='0'),False),(dict(MainPID='42',ActiveState='active',ExecStart='different producer'),True)]:
            with self.assertRaises(ValueError):followup.admissible_owner(live,relative,terminal)

    def prepared(self,root):
        source=root/'build/diagnostics/driver_output_shape/test';source.mkdir(parents=True);(source/'manifest.json').write_text('{}')
        out=root/'build/diagnostics/driver_shape_source_followup/test';out.mkdir(parents=True)
        owner=dict(MainPID='42',ActiveState='active',InvocationID='first',ExecStart='producer')
        (out/'manifest.json').write_text(json.dumps(dict(identity=dict(source=str(source.relative_to(root)),inputs={},unit='old',owner=owner))))
        return source,out,owner

    def test_failed_nominal_terminal_receipt_cannot_dispatch_source_matrix(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(followup,'ROOT',Path(tmp)):
            source,out,_=self.prepared(Path(tmp));(source/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,source_pilot_reference_checks_passed=False,manifest_sha256=followup.sha(source/'manifest.json'))))
            with patch.object(followup,'owner',return_value=dict(MainPID='0',ActiveState='inactive')),patch.object(followup.subprocess,'run',side_effect=AssertionError('Source matrix dispatched')):
                followup.run(out)
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_nominal_pilot_not_passed')

    def test_changed_live_owner_cannot_be_treated_as_completion(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(followup,'ROOT',Path(tmp)):
            _,out,owner=self.prepared(Path(tmp))
            with patch.object(followup,'owner',return_value=dict(owner,MainPID='43',InvocationID='second')):
                with self.assertRaisesRegex(ValueError,'Live prerequisite'):followup.run(out)

    def test_successful_source_run_may_have_an_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(followup,'ROOT',Path(tmp)):
            root=Path(tmp);source,out,_=self.prepared(root)
            (source/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,source_pilot_reference_checks_passed=True,manifest_sha256=followup.sha(source/'manifest.json'))))
            matrix=root/'build/diagnostics/driver_shape_source/test'
            def command(args,**kwargs):
                if 'prepare' in args:
                    matrix.mkdir(parents=True);(matrix/'manifest.json').write_text('{}')
                    kwargs['stdout'].write('/work/OpenLVDS/build/diagnostics/driver_shape_source/test\n')
                else:
                    (matrix/'summary.json').write_text(json.dumps(dict(source_waveform_matrix_passed=True,required_cases=30,required_pvt=15,passed_pvt=15,manifest_sha256=followup.sha(matrix/'manifest.json'))))
                return followup.subprocess.CompletedProcess(args,0)
            with patch.object(followup,'owner',return_value=dict(MainPID='0',ActiveState='inactive')),patch.object(followup.subprocess,'run',side_effect=command):
                followup.run(out)
            self.assertEqual((out/'run.log').read_text(),'')
            self.assertTrue(json.loads((out/'summary.json').read_text())['source_waveform_matrix_passed'])


if __name__=='__main__':unittest.main()
