# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Use scripts/env.sh')
class RXControlTests(unittest.TestCase):
    def test_actual_dll_to_payload_composition(self):
        modes = ('complete_scan_payload_and_clock_loss', 'unadmitted_dll',
                 'unadmitted_rom', 'unadmitted_deskew', 'unadmitted_dcc',
                 'missing_dll_settling', 'missing_deskew_settling',
                 'one_deadline_spans_dll_and_scan', 'retrain_recalibrates_and_rescans',
                 'forwarded_source_loss_after_payload', 'weakened_confirmation_count_rejected')
        baseline_lock_age = None
        with tempfile.TemporaryDirectory() as tmp:
            for mode, name in enumerate(modes):
                with self.subTest(mode=name):
                    binary = Path(tmp) / f'{mode}.vvp'
                    overrides = []
                    if mode in (6, 7):
                        self.assertIsNotNone(baseline_lock_age)
                        # Keep all 64 confirmations. Place the overall deadline
                        # after measured calibration, inside the following scan.
                        deadline = baseline_lock_age + (200 if mode == 6 else 1000)
                        overrides = [f'-Ptb_rx_control_v2.DEADLINE={deadline}']
                    build = subprocess.run([
                        'iverilog', '-g2012', '-Wall', '-s', 'tb_rx_control_v2',
                        f'-Ptb_rx_control_v2.MODE={mode}', *overrides, '-o', str(binary),
                        *map(str, sorted((ROOT / 'rtl/v2').glob('*.v'))),
                        str(ROOT / 'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                        str(ROOT / 'tb/tb_dcc_release_v2.v'),
                        str(ROOT / 'tb/tb_rx_control_v2.v')], capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180 if mode == 8 else 120)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertIn('PASS v2', run.stdout)
                    if mode == 0:
                        match = re.search(r'DLL_LOCK age=\s*(\d+)', run.stdout)
                        self.assertIsNotNone(match, run.stdout)
                        baseline_lock_age = int(match.group(1))
                    print(run.stdout, end='')
