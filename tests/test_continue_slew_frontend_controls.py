import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_slew_frontend_controls as handoff


class SourceControlsHandoff(unittest.TestCase):
    def test_owner_and_namespace_are_required_before_preparation(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)),patch.object(handoff.upstream,'owner',return_value={}) as owner:
            root=Path(d);parent=root/'build/diagnostics/dll_slew_verified_expansion_followup/p';base=root/'build/diagnostics/pfd_controls_baseline/b'
            with self.assertRaises(ValueError):handoff.prepare(root/'wrong','owner.service',base)
            owner.assert_not_called()
            with self.assertRaisesRegex(ValueError,'retained ownership'):handoff.prepare(parent,'owner.service',base)
            self.assertEqual(list(root.iterdir()),[])

    def test_expansion_requires_terminal_verification_and_unchanged_receipt(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)):
            root=Path(d);parent=root/'parent';parent.mkdir()
            state=parent/'state.json'
            for status in ('held_no_survivor','held_analog_fallback_required'):
                state.write_text(json.dumps({'status':status}));self.assertIsNone(handoff.admitted_expansion(parent))
            state.write_text(json.dumps({'status':'expanding'}))
            with self.assertRaises(ValueError):handoff.admitted_expansion(parent)
            state.write_text(json.dumps({'status':'expansion_verified','ranked_survivors':['nor4_inv4']}))
            rel=Path('build/diagnostics/dll_slew_expansion/e');p=root/rel;p.mkdir(parents=True);(p/'summary.json').write_text('{}')
            report=dict(artifact=str(rel),ranked_survivors=['nor4_inv4'],report_sha256=handoff.sha(p/'summary.json'))
            (parent/'summary.json').write_text(json.dumps(report));self.assertEqual(handoff.admitted_expansion(parent),rel)
            (p/'summary.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError):handoff.admitted_expansion(parent)
            for path in ('/work/OpenLVDS/build/diagnostics/wrong/e','/work/OpenLVDS/build/diagnostics/slew_frontend_controls/../wrong'):
                with self.assertRaises(ValueError):handoff.prepared_path(path,'slew_frontend_controls')

    def fixture(self,root):
        i=dict(parent='parent',unit='owner.service',owner={},baseline='baseline',files={},no_outer_lease=True)
        name=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        out=root/'build/diagnostics'/handoff.NAMESPACE/name;out.mkdir(parents=True)
        (out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False)))
        p=root/'parent';p.mkdir();(p/'state.json').write_text('{}')
        return out

    def test_no_survivor_never_dispatches_and_partial_handoff_cannot_retry(self):
        with tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)), \
             patch.object(handoff.upstream,'owner'),patch.object(handoff.upstream,'terminal',return_value=True), \
             patch.object(handoff,'admitted_expansion',return_value=None),patch.object(handoff.subprocess,'run') as run:
            out=self.fixture(Path(d));handoff.run(out)
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_no_source_survivor');run.assert_not_called()
            with self.assertRaisesRegex(ValueError,'no retry'):handoff.run(out)

    def test_controls_filter_source_and_failure_never_generates_source(self):
        for passed in (False,True):
            with self.subTest(passed=passed),tempfile.TemporaryDirectory() as d,patch.object(handoff,'ROOT',Path(d)), \
                 patch.object(handoff.upstream,'owner'),patch.object(handoff.upstream,'terminal',return_value=True), \
                 patch.object(handoff,'admitted_expansion',return_value=Path('build/diagnostics/dll_slew_expansion/e')):
                root=Path(d);out=self.fixture(root)
                controls=Path('build/diagnostics/slew_frontend_controls/c');source=Path('build/diagnostics/slew_pfd_source/s')
                for rel in (controls,source):
                    p=root/rel;p.mkdir(parents=True);(p/'manifest.json').write_text('{}')
                (root/controls/'summary.json').write_text(json.dumps(dict(source_controls_passed=passed,ranked_survivors=['nor4_inv4'] if passed else [])))
                def invoke(cmd,**kw):
                    text='{}'
                    if cmd[3:5]==['scripts/qualify_slew_frontend_controls.py','prepare']:text='/work/OpenLVDS/'+str(controls)
                    if cmd[3:5]==['scripts/prepare_controlled_slew_pfd.py','source']:text='/work/OpenLVDS/'+str(source)
                    return subprocess.CompletedProcess(cmd,0,stdout=text,stderr='')
                with patch.object(handoff.subprocess,'run',side_effect=invoke) as run:
                    handoff.run(out)
                state=json.loads((out/'state.json').read_text())
                self.assertEqual(state['status'],'controlled_source_verified' if passed else 'held_source_controls_failed')
                self.assertEqual(any(c.args[0][3:5]==['scripts/prepare_controlled_slew_pfd.py','source'] for c in run.call_args_list),passed)
                self.assertFalse(any('harden_slew_pfd.py' in c.args[0][3] for c in run.call_args_list))
