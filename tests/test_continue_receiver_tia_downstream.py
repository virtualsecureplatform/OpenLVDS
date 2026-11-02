# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_receiver_tia_downstream as handoff


class MatchedDownstream(unittest.TestCase):
    def test_unadmitted_native_or_components_return_without_reading_other_artifacts(self):
        for variant in handoff.VARIANTS:
            self.assertIsNone(handoff.admitted_native(dict(variant=variant,native_clock_passed=False),variant))
            self.assertIsNone(handoff.admitted_components(dict(variant=variant,components_passed=False),variant))
        with self.assertRaises(ValueError):handoff.admitted_native(dict(variant='other'),'tia_r2')

    def test_path_escape_and_other_namespaces_are_rejected(self):
        for p in ['/tmp/example','build/diagnostics/receiver_replay/../../escape','build/diagnostics/receiver_layout/x']:
            with self.assertRaises(ValueError):handoff.relative(p,'receiver_replay')

    def test_native_receipt_binds_exact_family_geometry_and_report(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            root=Path(tmp);rel=Path('build/diagnostics/receiver_replay/test');p=root/rel;p.mkdir(parents=True)
            layout='build/diagnostics/receiver_layout/test'
            (p/'manifest.json').write_text(json.dumps(dict(identity=dict(tia_restore_variant='tia_r2',layout=layout))))
            (p/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,native_clock_passed=True,manifest_sha256=handoff.sha(p/'manifest.json'))))
            row=dict(variant='tia_r2',native_clock_passed=True,root=str(rel),layout=layout,manifest_sha256=handoff.sha(p/'manifest.json'),report_sha256=handoff.sha(p/'summary.json'))
            self.assertEqual(handoff.admitted_native(row,'tia_r2'),(rel,Path(layout)))
            with self.assertRaises(ValueError):handoff.admitted_native(dict(row,layout='build/diagnostics/receiver_layout/other'),'tia_r2')
            (p/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'report changed'):handoff.admitted_native(row,'tia_r2')

    def test_incomplete_components_cannot_admit_rc_despite_receipt_flag(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            rel=Path('build/diagnostics/receiver_components/test');p=Path(tmp)/rel;p.mkdir(parents=True)
            (p/'manifest.json').write_text('{}')
            for passed in [59,60]:
                (p/'summary.json').write_text(json.dumps(dict(required=60,passed_cases=passed,passed=passed==60,manifest_sha256=handoff.sha(p/'manifest.json'))))
                row=dict(variant='tia_r2',components_passed=True,components=str(rel),manifest_sha256=handoff.sha(p/'manifest.json'),report_sha256=handoff.sha(p/'summary.json'))
                if passed==60:self.assertEqual(handoff.admitted_components(row,'tia_r2'),rel)
                else:
                    with self.assertRaisesRegex(ValueError,'all sixty'):handoff.admitted_components(row,'tia_r2')

    def test_each_variant_can_advance_without_waiting_for_the_other(self):
        barrier=threading.Barrier(2)
        def execute(v):barrier.wait(timeout=5);return v
        self.assertEqual(handoff.dispatch(handoff.VARIANTS,execute),handoff.VARIANTS)
        for bad in [[],['tia_r2','tia_r2'],['track_t8_r7']]:
            with self.assertRaises(ValueError):handoff.dispatch(bad,execute)

    def test_terminated_owner_without_report_cannot_trigger_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff,'owner',return_value=dict(MainPID='0')):
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'owner changed'):
                handoff.wait_result(root,'tia_r2','unit',dict(MainPID='123'),lambda:None,root/'state.json')
            self.assertFalse((root/'state.json').exists())

    def test_terminal_missing_variant_is_held_and_completion_race_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            root=Path(tmp)
            def ended(unit):
                (root/'summary.json').write_text(json.dumps(dict(results=[])))
                return dict(MainPID='0')
            with patch.object(handoff,'owner',side_effect=ended):
                row,proof=handoff.wait_result(root,'tia_r2','unit',dict(MainPID='123'),lambda:None,root/'state.json')
            self.assertEqual(row,dict(variant='tia_r2'))
            self.assertEqual(proof['sha256'],handoff.sha(root/'summary.json'))

    def test_other_source_family_cannot_attach_a_downstream_owner(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff,'owner') as owner:
            root=Path(tmp);source=root/'build/diagnostics/receiver_physical_followup/old';source.mkdir(parents=True)
            (source/'manifest.json').write_text(json.dumps(dict(matrix='build/diagnostics/receiver_differential_restore_matrix/old')))
            with self.assertRaises(ValueError):handoff.prepare('components',source,'unit')
            owner.assert_not_called()

    def test_prior_partial_state_is_preserved_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff.subprocess,'run') as launch:
            out=Path(tmp)/'build/diagnostics/receiver_tia_downstream/old';out.mkdir(parents=True)
            i=dict(stage='components',variants=handoff.VARIANTS,max_parallel_variants=2,no_outer_lease=True,files={})
            (out/'manifest.json').write_text(json.dumps(dict(identity=i)));(out/'state.json').write_text('retained')
            with self.assertRaisesRegex(ValueError,'Prior downstream'):handoff.run(out)
            self.assertEqual((out/'state.json').read_text(),'retained');launch.assert_not_called()
