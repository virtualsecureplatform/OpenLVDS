# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_dll_storage as storage


class StorageNativeQualification(unittest.TestCase):
    def test_incomplete_source_cannot_dispatch_any_native_or_source_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/dll_architecture/incomplete'; screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id='ss'), dict(id='tt'), dict(id='ff')])))
            with patch.object(storage, 'ROOT', root), patch.object(storage.source, 'validate'), patch.object(storage.source, 'run') as source_run, patch.object(storage.native, 'prepare') as native_prepare:
                with self.assertRaisesRegex(ValueError, 'Complete all three'):
                    storage.prepare(root/'layout', root/'pfd', screen)
                source_run.assert_not_called(); native_prepare.assert_not_called()

    def test_failed_source_cannot_be_relabelled_by_native_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/dll_architecture/failed'; screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id='ss'), dict(id='tt'), dict(id='ff')])))
            (screen/'summary.json').write_text('{"passed":true}')
            for name in ['ss', 'tt', 'ff']:
                folder = screen/name; folder.mkdir(); (folder/'summary.json').write_text(json.dumps(dict(passed=name!='ff')))
            with patch.object(storage, 'ROOT', root), patch.object(storage.source, 'validate'), patch.object(storage.source, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Every original'):
                    storage.source_gate(screen)
                run.assert_not_called()

    def test_profile_restores_scientific_and_resource_bindings(self):
        old = storage.native.CODE, storage.native.slot
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with storage.profile():
                self.assertIn(storage.NAME, storage.native.CODE)
                self.assertIn('screen_dll_storage.py', storage.native.CODE)
                self.assertIsNot(storage.native.slot, old[1])
                raise RuntimeError('injected')
        self.assertEqual((storage.native.CODE, storage.native.slot), old)

    def test_partial_native_trace_is_preserved_without_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'build/diagnostics/dll_qualification/partial'; out.mkdir(parents=True)
            folder = out/'loop_ss_0'; folder.mkdir(); raw = folder/'bench.raw'; raw.write_bytes(b'original partial trace')
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(variant=storage.VARIANT, screen='source'), tasks=[dict(id='loop_ss_0')])))
            (out/'storage_source_admission.json').write_text(json.dumps(dict(variant=storage.VARIANT,
                manifest_sha256=storage.sha(out/'manifest.json'), producer_sha256=storage.sha(Path(storage.__file__)), proofs={})))
            with patch.object(storage, 'ROOT', root), patch.object(storage, 'source_gate', return_value={}), patch.object(storage.native, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial 16 pF native output retained'):
                    storage.run(out)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'original partial trace')


if __name__ == '__main__':
    unittest.main()
