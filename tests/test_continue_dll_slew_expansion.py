import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_dll_slew_expansion as followup


class ExpansionHandoff(unittest.TestCase):
    def fixture(self, root):
        parent = root / 'handoff'; parent.mkdir()
        rel = Path('build/diagnostics/dll_slew_screen/screen')
        screen = root / rel; screen.mkdir(parents=True)
        (screen / 'manifest.json').write_text('{}')
        (screen / 'summary.json').write_text(json.dumps({'ranked_survivors': ['clkbuf_4']}))
        (parent / 'prepared.json').write_text(json.dumps(dict(artifact=str(rel), manifest_sha256=followup.sha(screen / 'manifest.json'))))
        report = dict(artifact=str(rel), report_sha256=followup.sha(screen / 'summary.json'), ranked_survivors=['clkbuf_4'])
        (parent / 'summary.json').write_text(json.dumps(report))
        return parent, screen, rel, report

    def test_terminal_receipt_binds_artifact_manifest_report_and_survivors(self):
        for mutation in ('none', 'manifest', 'report', 'survivors', 'path'):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d); parent, screen, rel, r = self.fixture(root)
                if mutation == 'manifest': (screen / 'manifest.json').write_text('{"changed": true}')
                if mutation == 'report': (screen / 'summary.json').write_text('{}')
                if mutation == 'survivors': r['ranked_survivors'] = []
                if mutation == 'path': r['artifact'] = 'build/diagnostics/dll_slew_screen/../../elsewhere'
                (parent / 'summary.json').write_text(json.dumps(r))
                with patch.object(followup, 'ROOT', root):
                    if mutation == 'none': self.assertEqual(followup.completed_screen(parent)[0], rel)
                    else:
                        with self.assertRaises(ValueError): followup.completed_screen(parent)

    def test_wrong_or_restarted_owner_cannot_prepare_expansion(self):
        root = followup.ROOT / 'build/diagnostics/dll_slew_screen_followup/example'
        for live in [dict(ActiveState='inactive'), dict(ActiveState='active', MainPID='12', InvocationID='abc', ExecStart='other.py example')]:
            with patch.object(followup, 'owner', return_value=live), self.assertRaises(ValueError):
                followup.prepare(root, 'unit')

    def test_failed_screen_owner_is_not_terminal_success(self):
        saved = dict(MainPID='12', InvocationID='abc')
        now = dict(MainPID='0', InvocationID='abc', LoadState='loaded', Result='exit-code', ExecMainStatus='1')
        with self.assertRaises(ValueError): followup.terminal(saved, now)
