import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_dll_analog_frontend_timing as handoff


class AnalogTimingHandoff(unittest.TestCase):
    def fixture(self,root):
        parent=root/'parent';parent.mkdir();(parent/'state.json').write_text('{}')
        i=dict(parent='parent',unit='owner.service',owner={},clock_baseline='baseline',files={},no_outer_lease=True)
        name=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        out=root/'build/diagnostics'/handoff.NAMESPACE/name;out.mkdir(parents=True)
        (out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False)))
        return out

    def test_owner_and_namespaces_required_before_preparation(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner',return_value={}):
            root=Path(d);base=root/'build/diagnostics/pfd_controls_baseline/b'
            with self.assertRaises(ValueError):handoff.prepare(root/'wrong','owner.service',base)
            with self.assertRaises(ValueError):handoff.prepare(root/'build/diagnostics/dll_analog_frontend_dc_followup/p','owner.service',base)
            self.assertEqual(list(root.iterdir()),[])

    def test_only_independently_verified_unchanged_dc_receipt_is_admitted(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)):
            root=Path(d);parent=root/'parent';parent.mkdir();state=parent/'state.json'
            for status in ('held_standard_cell_survivor','held_analog_headroom_failed'):
                state.write_text(json.dumps({'status':status}));self.assertIsNone(handoff.dc_artifact(parent))
            state.write_text(json.dumps({'status':'probing_analog_dc'}))
            with self.assertRaises(ValueError):handoff.dc_artifact(parent)
            rel=Path('build/diagnostics/dll_analog_frontend_dc/dc');dc=root/rel;dc.mkdir(parents=True);(dc/'summary.json').write_text('{}')
            ready=['tail140_w40'];state.write_text(json.dumps(dict(status='analog_dc_verified',artifact=str(rel),dc_ready_variants=ready)))
            (parent/'summary.json').write_text(json.dumps(dict(artifact=str(rel),dc_ready_variants=ready,report_sha256=handoff.sha(dc/'summary.json'))))
            self.assertEqual(handoff.dc_artifact(parent),rel)
            (dc/'summary.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError):handoff.dc_artifact(parent)
        for path in ('/work/OpenLVDS/build/diagnostics/wrong/t','/work/OpenLVDS/build/diagnostics/dll_analog_frontend_timing/../wrong'):
            with self.assertRaises(ValueError):handoff.prepared_path(path)

    def test_no_dc_survivor_never_dispatches_and_partial_handoff_cannot_retry(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner'), \
             patch.object(handoff.owner_policy,'terminal',return_value=True),patch.object(handoff,'dc_artifact',return_value=None), \
             patch.object(handoff.subprocess,'run') as run:
            out=self.fixture(Path(d));handoff.run(out);run.assert_not_called()
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_no_analog_dc_survivor')
            with self.assertRaisesRegex(ValueError,'no retry'):handoff.run(out)

    def test_ready_dc_runs_and_verifies_only_source_timing(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.owner_policy,'owner'), \
             patch.object(handoff.owner_policy,'terminal',return_value=True),patch.object(handoff,'dc_artifact',return_value=Path('build/diagnostics/dll_analog_frontend_dc/dc')):
            root=Path(d);out=self.fixture(root);rel=Path('build/diagnostics/dll_analog_frontend_timing/t');artifact=root/rel;artifact.mkdir(parents=True)
            (artifact/'manifest.json').write_text('{}');(artifact/'summary.json').write_text(json.dumps({'ranked_survivors':['tail140_w40']}))
            def invoke(cmd,**kw):
                return subprocess.CompletedProcess(cmd,0,stdout='/work/OpenLVDS/'+str(rel) if cmd[4]=='prepare' else '{}',stderr='')
            with patch.object(handoff.subprocess,'run',side_effect=invoke) as run:handoff.run(out)
            self.assertEqual([c.args[0][4] for c in run.call_args_list],['prepare','run','verify'])
            self.assertEqual(run.call_args_list[0].args[0][-2:],['--clock-baseline','baseline'])
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'analog_timing_verified')
            self.assertFalse(json.loads((out/'summary.json').read_text())['qualified_phy'])
