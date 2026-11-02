# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_receiver_spec_rc as handoff


class ReceiverRcHandoff(unittest.TestCase):
    def test_component_selection_requires_bound_sixty_case_pass(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            relative=Path('build/diagnostics/receiver_components/test');out=Path(tmp)/relative;out.mkdir(parents=True)
            (out/'manifest.json').write_text('{}')
            result=dict(passed=True,required=60,passed_cases=60,manifest_sha256=handoff.sha(out/'manifest.json'))
            (out/'summary.json').write_text(json.dumps(result))
            report=dict(components_passed=True,components=str(relative),report_sha256=handoff.sha(out/'summary.json'))
            self.assertEqual(handoff.selected_components(None,report),relative)
            self.assertIsNone(handoff.selected_components(None,dict(report,components_passed=False)))
            for changed in [dict(result,passed_cases=59),dict(result,passed=False),dict(result,manifest_sha256='changed')]:
                (out/'summary.json').write_text(json.dumps(changed));r=dict(report,report_sha256=handoff.sha(out/'summary.json'))
                with self.assertRaises(ValueError):handoff.selected_components(None,r)

    def test_completed_component_paths_cannot_escape_namespace(self):
        for value in ['/tmp/components','build/diagnostics/receiver_components/../other','build/diagnostics/receiver_replay/test']:
            with self.assertRaisesRegex(ValueError,'Unexpected completed'):handoff.selected_components(None,dict(components_passed=True,components=value))

    def test_only_exact_live_verified_owner_can_prepare(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            source=Path(tmp)/'build/diagnostics/receiver_spec_verified_followup/test'
            for live in [dict(MainPID='0',ActiveState='inactive'),dict(MainPID='42',ActiveState='active',ExecStart='scripts/continue_receiver_spec_verified.py run other')]:
                with patch.object(handoff,'owner',return_value=live):
                    with self.assertRaisesRegex(ValueError,'exact live'):handoff.prepare(source,'producer')

    def test_terminal_held_receipt_survives_owner_unload_without_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            root=Path(tmp);source=root/'build/diagnostics/receiver_spec_verified_followup/test';source.mkdir(parents=True)
            (source/'manifest.json').write_text('{}');(source/'summary.json').write_text(json.dumps(dict(components_passed=False,manifest_sha256=handoff.sha(source/'manifest.json'))))
            out=root/'build/diagnostics/receiver_spec_rc_followup/test';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(source=str(source.relative_to(root)),inputs={},unit='old',owner={}))))
            with patch.object(handoff,'owner',side_effect=AssertionError('Unloaded terminal owner queried')),patch.object(handoff.subprocess,'run',side_effect=AssertionError('Held work dispatched')):
                handoff.run(out)
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_components_not_passed')


if __name__=='__main__':unittest.main()
