# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import validate_receiver_differential_restore_rc as comparison


class DifferentialRestoreReceiverRc(unittest.TestCase):
    def campaign(self,root,completed=60):
        requirements=dict(process_corners=['tt','ff','ss','fs','sf'],temperatures_c=[0,25,40])
        (root/'requirements.json').write_text(json.dumps(requirements))
        out=root/'build/diagnostics/receiver_components/test';out.mkdir(parents=True)
        tasks=[dict(id=f'{view}_{test}_{process}_{temperature}',view=view,test=test,process=process,temperature=temperature)
            for view,test,process,temperature in itertools.product(['schematic','native'],['receiver','receiver_rate'],
                requirements['process_corners'],requirements['temperatures_c'])]
        (out/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        (out/'summary.json').write_text(json.dumps(dict(required=60,passed_cases=60,passed=True)))
        for task in tasks[:completed]:
            folder=out/task['id'];folder.mkdir();(folder/'summary.json').write_text('{}')
        return out

    def test_missing_component_report_cannot_dispatch_a_prerequisite(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(comparison,'ROOT',Path(tmp)):
            out=self.campaign(Path(tmp),59)
            with patch.object(comparison.qualification,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all sixty'):
                    comparison.component_gate(out)
                run.assert_not_called()

    def test_failed_components_cannot_request_cached_remeasurement_or_rc(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(comparison,'ROOT',Path(tmp)):
            out=self.campaign(Path(tmp))
            (out/'summary.json').write_text(json.dumps(dict(required=60,passed_cases=59,passed=False)))
            with patch.object(comparison.qualification,'run') as run:
                with self.assertRaisesRegex(ValueError,'must pass all sixty'):
                    comparison.component_gate(out)
                run.assert_not_called()

    def test_other_namespace_is_refused_before_any_measurement(self):
        with patch.object(comparison.qualification,'run') as run:
            with self.assertRaisesRegex(ValueError,'isolated original differential-restoration'):
                comparison.component_gate(Path('/tmp/unrelated'))
            run.assert_not_called()

    def test_native_and_component_layouts_must_match_before_model_assembly(self):
        with patch.object(comparison.qualification,'selected',return_value=dict(layout='another/layout')),patch.object(comparison,'audited') as audit:
            with self.assertRaisesRegex(ValueError,'geometry differ'):
                comparison.physical_model(dict(replay='replay',layout='selected/layout'))
            audit.assert_not_called()

    def test_profile_restores_after_failure_and_selects_only_declared_views(self):
        previous=comparison.validation.library,comparison.validation.slot
        views=dict(full=(b'full',{'receiver':'native'}),fast=(b'fast',{'receiver':'approximate'}))
        with self.assertRaises(RuntimeError):
            with comparison.profile(views):
                self.assertEqual(comparison.validation.library(fast=False),(b'full',{'receiver':'native'},{}))
                self.assertEqual(comparison.validation.library(fast=True),(b'fast',{'receiver':'approximate'},{}))
                raise RuntimeError('injected')
        self.assertEqual((comparison.validation.library,comparison.validation.slot),previous)

    def test_cache_recipe_retains_original_full_sixty_ns_fixture(self):
        with patch.dict('os.environ',{'PDK_ROOT':'/opt/pdk/test'}),patch.object(comparison,'engine',return_value='ngspice'),patch.object(comparison,'closure_hash',return_value='abcdef0123456789'):
            body,nodes=comparison.validation.fixture('receiver',{})
            recipe=hashlib.sha256(json.dumps([body,nodes,'60n','100p','/opt/pdk/test/sky130A/libs.tech/ngspice/sky130.lib.spice',comparison.validation.REQUIREMENTS_HASH]).encode()).hexdigest()
            folder=comparison.case_path(b'library','full','runtime123456789')
            self.assertEqual(folder.name,'full_abcdef0123_runtime123_'+recipe[:10])


if __name__=='__main__':
    unittest.main()
