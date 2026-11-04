# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import drain_legacy_clocking as drain


class DrainTests(unittest.TestCase):
    def test_unrelated_pid_never_signalled(self):
        with patch.object(drain, 'proc', return_value=None), patch.object(drain.os, 'kill') as kill:
            with self.assertRaises(ValueError):
                drain.begin(42, drain.ROOT / drain.ALLOWED['extend_rx_aperture.py'] / 'case', 'extend_rx_aperture.py')
            kill.assert_not_called()

    def fixture(self, root):
        artifact = root / 'old'; artifact.mkdir()
        (artifact / 'manifest.json').write_text('{}')
        out = root / 'receipt'; out.mkdir()
        coordinator = dict(pid=42, start='123', state='T')
        (out / 'identity.json').write_text(json.dumps(dict(coordinator=coordinator,
            artifact='old', manifest_sha256=drain.digest(artifact / 'manifest.json'))))
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
