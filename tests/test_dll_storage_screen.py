# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_dll_storage as screen


class DllStorageScreen(unittest.TestCase):
    def test_library_preserves_native_pfd_delay_and_bias(self):
        blocks = []
        for top in ['lvds_bias', 'lvds_pfd', 'openlvds_delay_line', screen.TOP]:
            blocks.append(f'.subckt {top} A B\n'
                          'XCAP A B sky130_fd_pr__cap_mim_m3_1 w=10 l=10\n'
                          f'.ends {top}\n')
        base = '\n'.join(blocks)
        source = blocks[-1].replace('w=10 l=10', 'w=30 l=30')
        result = screen.library(base, source)
        for top in ['lvds_bias', 'lvds_pfd', 'openlvds_delay_line']:
            self.assertEqual(screen.closure_hash(base, top), screen.closure_hash(result, top))
        self.assertNotEqual(screen.closure_hash(base, screen.TOP), screen.closure_hash(result, screen.TOP))
        # Actual source fixtures inline the delay devices into the analog
        # macro and have no separate openlvds_delay_line definition.
        flattened = base.replace(blocks[2], '')
        self.assertIn('.subckt '+screen.TOP, screen.library(flattened, source))

    def test_frozen_producer_bindings_restore_after_exception(self):
        original = screen.reference.validate, screen.reference.slot
        with self.assertRaises(RuntimeError):
            with screen.profile():
                self.assertIs(screen.reference.validate, screen.validate)
                raise RuntimeError('test failure')
        self.assertEqual(original, (screen.reference.validate, screen.reference.slot))

    def test_partial_source_run_is_preserved_without_simulator_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); case = root/'build/diagnostics/dll_architecture/test'
            (case/'task').mkdir(parents=True)
            (case/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id='task')])))
            raw = case/'task/bench.raw'; raw.write_bytes(b'partial retained')
            with patch.object(screen, 'ROOT', root), patch.object(screen, 'validate'), \
                    patch.object(screen.reference, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial storage acquisition'):
                    screen.run(case)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'partial retained')


if __name__ == '__main__':
    unittest.main()
