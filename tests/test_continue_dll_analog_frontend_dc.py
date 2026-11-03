import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_dll_analog_frontend_dc as handoff


class AnalogFrontendHandoff(unittest.TestCase):
    def fixture(self,root,survivors=()):
        parent=root/'screen';parent.mkdir();(parent/'manifest.json').write_text('{}')
        (parent/'summary.json').write_text(json.dumps({'ranked_survivors':list(survivors)}))
        identity=dict(parent='screen',unit='owner.service',owner={},files={},no_outer_lease=True)
        name=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        out=root/'build/diagnostics'/handoff.NAMESPACE/name;out.mkdir(parents=True)
        (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False)))
        return out

    def test_missing_or_nonretained_owner_cannot_prepare(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner',return_value={}):
            root=Path(d)
            with self.assertRaises(ValueError):handoff.prepare(root/'wrong','owner.service')
            with self.assertRaises(ValueError):handoff.prepare(root/'build/diagnostics/dll_slew_screen/s','owner.service')
            self.assertEqual(list(root.iterdir()),[])

    def test_standard_survivor_blocks_analog_prototype_and_handoff_cannot_retry(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner'), \
             patch.object(handoff.owner_policy,'terminal',return_value=True), \
             patch.object(handoff.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='{}',stderr='')) as run:
            out=self.fixture(Path(d),['nor4_inv4']);handoff.run(out)
            self.assertEqual(run.call_count,1);self.assertIn('screen_dll_slew_frontends.py',run.call_args.args[0][3])
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_standard_cell_survivor')
            with self.assertRaisesRegex(ValueError,'no retry'):handoff.run(out)

    def test_no_survivors_dispatches_only_dc_and_preserves_failed_headroom(self):
        for ready in ([],['tail140_w40']):
            with self.subTest(ready=ready),tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)), \
                 patch.object(handoff.owner_policy,'owner'),patch.object(handoff.owner_policy,'terminal',return_value=True):
                root=Path(d);out=self.fixture(root);rel=Path('build/diagnostics/dll_analog_frontend_dc/dc')
                artifact=root/rel;artifact.mkdir(parents=True);(artifact/'manifest.json').write_text('{}')
                (artifact/'summary.json').write_text(json.dumps(dict(dc_ready_variants=ready)))
                def invoke(cmd,**kwargs):
                    text='/work/OpenLVDS/'+str(rel) if cmd[3:5]==['scripts/probe_dll_analog_frontend_dc.py','prepare'] else '{}'
                    return subprocess.CompletedProcess(cmd,0,stdout=text,stderr='')
                with patch.object(handoff.subprocess,'run',side_effect=invoke) as run:handoff.run(out)
                self.assertEqual(run.call_count,4)
                self.assertEqual(json.loads((out/'state.json').read_text())['status'],'analog_dc_verified' if ready else 'held_analog_headroom_failed')
                report=json.loads((out/'summary.json').read_text());self.assertFalse(report['timing_repair_verified']);self.assertFalse(report['qualified_phy'])
                self.assertTrue(all(c.args[0][3] in ['scripts/screen_dll_slew_frontends.py','scripts/probe_dll_analog_frontend_dc.py'] for c in run.call_args_list))

    def test_failed_verification_cannot_prepare_circuit_and_foreign_path_is_refused(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner'), \
             patch.object(handoff.owner_policy,'terminal',return_value=True), \
             patch.object(handoff.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stdout='',stderr='failed')) as run:
            out=self.fixture(Path(d))
            with self.assertRaises(subprocess.CalledProcessError):handoff.run(out)
            self.assertEqual(run.call_count,1);self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_for_diagnosis')
        for path in ('/work/OpenLVDS/build/diagnostics/wrong/dc','/work/OpenLVDS/build/diagnostics/dll_analog_frontend_dc/../wrong'):
            with self.assertRaises(ValueError):handoff.prepared_path(path)
