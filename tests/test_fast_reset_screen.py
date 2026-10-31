# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import screen_fast_reset_dll as screen
from dll_design import candidate_source, native_block
from dll_campaign import text_block
from layout import circuits
from repair_dll_monitor import repaired_source

ROOT = Path(__file__).resolve().parents[1]


class FastResetScreen(unittest.TestCase):
    def test_proposed_source_preserves_every_other_circuit(self):
        source = repaired_source(candidate_source((ROOT / 'analog/openlvds.spice').read_text(), 'ota_w8_c4',
                                 (ROOT / 'analog/experiments/phase_area.spice').read_text()))
        result = screen.candidate_source(source)
        self.assertEqual(native_block(source, 'openlvds_dll_analog'), native_block(result, 'openlvds_dll_analog'))
        self.assertNotEqual(text_block(source, 'lvds_pfd'), text_block(result, 'lvds_pfd'))
        for name in circuits(source):
            if name != 'lvds_pfd':
                self.assertEqual(text_block(source, name), text_block(result, name))

    def controls(self, root):
        capture = root / 'capture'; capture.mkdir(); tasks = []
        for offset in [-850, 850, 0]:
            folder = capture / str(offset); folder.mkdir()
            for name in ['library.spice', 'bench.cir', 'bench.cir.prn', 'bench.raw']:
                (folder / name).write_text(name)
            tasks.append(dict(id=str(offset), offset_ps=offset, aliases=dict(UP='UP', DN='DN'),
                              files={n: screen.digest(folder / n) for n in ['library.spice', 'bench.cir']}))
        (capture / 'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        for task in tasks:
            folder = capture / task['id']; offset = task['offset_ps']
            report = dict(manifest_sha256=screen.digest(capture / 'manifest.json'),
                          raw_difference_v=.6 if offset > 0 else -.6 if offset < 0 else 0,
                          correct_area_sign=True,
                          files={n: screen.digest(folder / n) for n in ['library.spice', 'bench.cir', 'bench.cir.prn', 'bench.raw']})
            (folder / 'summary.json').write_text(json.dumps(report))
        return capture, dict(identity=dict(capture='capture'))

    def wave(self, path):
        offset = int(path.parent.name); up, dn = (.3, .9) if offset < 0 else (.9, .3) if offset > 0 else (.3, .3)
        return np.array([[0, 0, up, dn], [1, 60e-9, up, dn], [2, 80e-9, up, dn]]), {'V(UP)': 2, 'V(DN)': 3}

    def test_admission_rejects_missing_and_wrong_sign_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); capture, manifest = self.controls(root)
            with patch.object(screen, 'ROOT', root), patch.object(screen, 'read_wave', side_effect=self.wave):
                screen.capture_admission(root, manifest)
                (capture / '0/summary.json').unlink()
                with self.assertRaisesRegex(ValueError, 'still pending'):
                    screen.capture_admission(root, manifest)

    def test_green_report_cannot_hide_a_wrong_waveform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, manifest = self.controls(root)
            def wrong_wave(path):
                w, h = self.wave(path)
                if path.parent.name == '-850':
                    w[:, 2:] = w[:, [3, 2]]
                return w, h
            with patch.object(screen, 'ROOT', root), patch.object(screen, 'read_wave', side_effect=wrong_wave):
                with self.assertRaisesRegex(ValueError, 'differs from its waveform'):
                    screen.capture_admission(root, manifest)
