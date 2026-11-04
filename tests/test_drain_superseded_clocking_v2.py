# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import drain_superseded_clocking_v2 as drain


class DrainTests(unittest.TestCase):
    def test_namespace_pid_alias_does_not_archive_another_campaign_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ['mine','other']:(root/(name+'.owner')).write_text(name)
            descriptors={drain.file_identity(root/'mine.owner')}
            self.assertTrue(drain.owned_ticket(root,dict(id='mine',pid=14),descriptors))
            self.assertFalse(drain.owned_ticket(root,dict(id='other',pid=14),descriptors))
            self.assertFalse(drain.owned_ticket(root,dict(id='missing',pid=14),descriptors))

    def test_valid_reason_still_cannot_signal_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=root/'build/diagnostics/evidence.json';evidence.parent.mkdir(parents=True);evidence.write_text('{}')
            artifact=root/drain.ALLOWED['expand_analog_arbiter_v2.py']/'case'
            with patch.object(drain,'ROOT',root),patch.object(drain,'proc',return_value=None),patch.object(drain.os,'kill') as kill:
                with self.assertRaisesRegex(ValueError,'identity mismatch'):
                    drain.begin(42,artifact,'expand_analog_arbiter_v2.py','Replaced by a separately measured physical circuit',[evidence])
                kill.assert_not_called()

    def test_unrelated_pid_never_signalled(self):
        with patch.object(drain, 'proc', return_value=None), patch.object(drain.os, 'kill') as kill:
            with self.assertRaises(ValueError):
                drain.begin(42, drain.ROOT / drain.ALLOWED['expand_analog_arbiter_v2.py'] / 'case', 'expand_analog_arbiter_v2.py')
            kill.assert_not_called()

    def fixture(self, root):
        artifact = root / 'old'; artifact.mkdir()
        (artifact / 'manifest.json').write_text('{}')
        out = root / 'receipt'; out.mkdir()
        coordinator = dict(pid=42, start='123', state='T')
        (out / 'identity.json').write_text(json.dumps(dict(coordinator=coordinator,
            artifact='old', manifest_sha256=drain.digest(artifact / 'manifest.json'),
            producer_sha256=drain.digest(Path(drain.__file__)),evidence_files={})))
        return artifact, out, coordinator

    def test_active_exporter_prevents_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out, coordinator = self.fixture(Path(tmp))
            with patch.object(drain, 'ROOT', Path(tmp)), patch.object(drain, 'proc', return_value=coordinator), \
                 patch.object(drain, 'descendants', return_value=[dict(pid=43)]), patch.object(drain.os, 'kill') as kill:
                self.assertEqual(drain.finish(out)['status'], 'draining_children')
                kill.assert_not_called()

    def test_pid_reuse_never_signalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out, _ = self.fixture(Path(tmp))
            with patch.object(drain, 'proc', return_value=dict(start='124', state='T')), patch.object(drain.os, 'kill') as kill:
                with self.assertRaises(ValueError): drain.finish(out)
                kill.assert_not_called()

    def test_changed_evidence_prevents_any_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,out,coordinator=self.fixture(root)
            proof=root/'proof.json';proof.write_text('{}')
            identity=json.loads((out/'identity.json').read_text());identity['evidence_files']={'proof.json':drain.digest(proof)}
            (out/'identity.json').write_text(json.dumps(identity));proof.write_text('{"changed":true}')
            with patch.object(drain,'ROOT',root),patch.object(drain,'proc',return_value=coordinator),patch.object(drain.os,'kill') as kill:
                with self.assertRaisesRegex(ValueError,'superseding evidence changed'):drain.finish(out)
                kill.assert_not_called()

    def test_only_stopped_coordinator_retired_original_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); artifact, out, coordinator = self.fixture(root)
            case = artifact / 'case'; case.mkdir()
            for name in ['bench.cir', 'bench.raw', 'bench.cir.prn']:
                (case / name).write_text(name)
            before = {p: p.read_bytes() for p in artifact.rglob('*') if p.is_file()}
            with patch.object(drain, 'ROOT', root), patch.object(drain, 'proc', return_value=coordinator), \
                 patch.object(drain, 'descendants', return_value=[]), patch.object(drain.os, 'kill') as kill:
                result = drain.finish(out)
                self.assertEqual(result['status'], 'archived_incomplete')
                self.assertEqual(result['completed_summaries'], 0)
                kill.assert_called_once_with(42, signal.SIGKILL)
            self.assertEqual(before, {p: p.read_bytes() for p in artifact.rglob('*') if p.is_file()})
