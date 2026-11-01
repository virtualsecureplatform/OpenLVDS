# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_driver_restore_components as followup


class DriverRestoreFollowup(unittest.TestCase):
    def fixture(self, root):
        scripts = root/'scripts';scripts.mkdir()
        (scripts/Path(followup.__file__).name).write_bytes(Path(followup.__file__).read_bytes())
        (scripts/'env.sh').write_text('environment')
        (scripts/'qualify_driver_restore_components.py').write_text('producer')
        comparison = root/'build/diagnostics/driver_native_restore/selected';comparison.mkdir(parents=True)
        layout = 'build/diagnostics/driver_layout/selected'
        (comparison/'manifest.json').write_text(json.dumps(dict(identity=dict(layouts={'restore_64_24':layout}))))
        results=[]
        for name in sorted(followup.CASES):
            (comparison/name).mkdir()
            child=dict(task=name,diagnostic_complete=True,native_driver_only=True)
            (comparison/name/'summary.json').write_text(json.dumps(child));results.append(child)
        (comparison/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,native_driver_only=True,
            manifest_sha256=followup.digest(comparison/'manifest.json'),results=results)))
        artifact = root/'build/diagnostics/driver_components/selected';artifact.mkdir(parents=True)
        identity=dict(comparison=str(comparison.relative_to(root)),layout=layout,variant='restore_64_24',
            code={'qualify_driver_restore_components.py':followup.digest(scripts/'qualify_driver_restore_components.py')},
            inputs={str((comparison/'manifest.json').relative_to(root)):followup.digest(comparison/'manifest.json')})
        (artifact/'manifest.json').write_text(json.dumps(dict(identity=identity)))
        return artifact,comparison

    def test_complete_native_manifest_and_both_actual_child_reports_required(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact,comparison=self.fixture(Path(temp))
            followup.native_complete(comparison)
            report=comparison/'summary.json';summary=json.loads(report.read_text())
            for change in [dict(manifest_sha256='wrong'),dict(results=[summary['results'][0]]),dict(diagnostic_complete=False)]:
                report.write_text(json.dumps(dict(summary,**change)))
                with self.assertRaisesRegex(ValueError,'incomplete'):
                    followup.native_complete(comparison)
            report.write_text(json.dumps(summary))
            (comparison/'source_control/summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'child differs'):
                followup.native_complete(comparison)

    def test_waits_for_owner_and_uses_actual_component_report_not_exit_status(self):
        for outcome in ['passed','native_failure','component_failure','wrong_manifest']:
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);artifact,comparison=self.fixture(root);calls=[]
                def child(command,**kwargs):
                    calls.append(command)
                    if command[0]=='systemctl':
                        active=len(calls)==1
                        value=('ActiveState=active\nResult=success\nExecMainStatus=0\n' if active else
                               'ActiveState=inactive\nResult=success\nExecMainStatus=0\n')
                        if not active and outcome=='native_failure':
                            value='ActiveState=failed\nResult=exit-code\nExecMainStatus=1\n'
                        return followup.subprocess.CompletedProcess(command,0,stdout=value)
                    self.assertEqual(len(calls),3)
                    self.assertEqual(command[-3:], [str(artifact.relative_to(root)),'--jobs','2'])
                    (artifact/'summary.json').write_text(json.dumps(dict(passed=outcome!='component_failure',
                        manifest_sha256='wrong' if outcome=='wrong_manifest' else followup.digest(artifact/'manifest.json'))))
                    return followup.subprocess.CompletedProcess(command,0)
                with patch.object(followup,'ROOT',root),patch.object(followup.subprocess,'run',side_effect=child), \
                     patch.object(followup.time,'sleep'):
                    if outcome=='passed':followup.run(artifact,'matched.service')
                    else:
                        with self.assertRaises(ValueError):followup.run(artifact,'matched.service')
                state=json.loads(next((artifact/'followup').glob('*/state.json')).read_text())
                self.assertEqual(state['status'],'components_passed' if outcome=='passed' else 'held_for_diagnosis')
                self.assertFalse(state['qualified_phy'])
                self.assertEqual(len(calls),2 if outcome=='native_failure' else 3)

    def test_changed_or_different_variant_capture_holds_before_any_owner_query(self):
        for broken in ['layout','comparison_hash','producer_hash']:
            with self.subTest(broken=broken),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);artifact,comparison=self.fixture(root)
                path=artifact/'manifest.json';manifest=json.loads(path.read_text());identity=manifest['identity']
                if broken=='layout':identity['layout']='build/diagnostics/driver_layout/another'
                elif broken=='comparison_hash':identity['inputs'][str((comparison/'manifest.json').relative_to(root))]='wrong'
                else:identity['code']['qualify_driver_restore_components.py']='wrong'
                path.write_text(json.dumps(manifest))
                with patch.object(followup,'ROOT',root),patch.object(followup.subprocess,'run') as run:
                    with self.assertRaises(ValueError):followup.run(artifact,'matched.service')
                    run.assert_not_called()


if __name__=='__main__':unittest.main()
