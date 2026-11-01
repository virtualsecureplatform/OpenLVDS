# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import driver_current_native as current
import qualify_driver_current_components as full
from driver_restore_variant import source_variant

ROOT = Path(__file__).resolve().parents[1]


class CorrectedDriverQualification(unittest.TestCase):
    def test_profile_restores_model_validator_and_resource_lease_on_exception(self):
        n = current.native; previous = n.physical_models, n.CODE, n.slot
        with self.assertRaises(RuntimeError):
            with current.profile():
                self.assertIs(n.physical_models, current.physical_models)
                self.assertIn(current.NAME, n.CODE)
                raise RuntimeError('test failure')
        self.assertEqual(previous, (n.physical_models, n.CODE, n.slot))

    def test_old_p64_n24_layout_cannot_substitute_for_current_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'analog').mkdir()
            source = (ROOT/'analog/openlvds.spice').read_text(); (root/'analog/openlvds.spice').write_text(source)
            folder = root/'build/diagnostics/driver_layout/old'; folder.mkdir(parents=True)
            (folder/'candidate.spice').write_text(source_variant(source))
            (folder/'summary.json').write_text(json.dumps(dict(passed=True, identity=dict(variant='restore_64_24'))))
            (folder/'extraction.json').write_text('{}')
            layouts = {'restore_64_24': folder, 'source_control': folder}
            with patch.object(current, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'declared 110:1'):
                    current.physical_models(layouts)

    def partial(self, root, name, digest):
        folder = root/'case'; folder.mkdir(); (folder/'bench.raw').write_bytes(b'preserved partial raw')
        (root/'manifest.json').write_text(json.dumps(dict(identity=dict(code={name: digest}), tasks=[dict(id='case')])))
        return folder/'bench.raw'

    def test_partial_native_run_is_preserved_before_any_simulator_can_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = self.partial(root, current.NAME, current.native.digest(Path(current.__file__)))
            with patch.object(current.native, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial native'):
                    current.run(root)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'preserved partial raw')

    def test_partial_full_component_run_is_preserved_before_any_worker_can_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = self.partial(root, full.NAME, full.component.digest(Path(full.__file__)))
            with patch.object(full.component, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial component'):
                    full.run(root, 1)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'preserved partial raw')


if __name__ == '__main__':
    unittest.main()
