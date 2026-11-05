# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Use scripts/env.sh')
class RXTrainingV3Tests(unittest.TestCase):
    def test_composed_rx_scan_and_physical_transaction_protocol(self):
        modes = ('scan_payload_and_delivered_phase_loss', 'missing_physical_settling',
                 'wrong_settling_tag', 'unadmitted_rom', 'unadmitted_deskew',
                 'unadmitted_dcc', 'missing_dll_lock', 'single_overall_deadline',
                 'source_loss_during_hold', 'retrain_cancels_pending_update',
                 'dll_lock_loss', 'dll_failure', 'table_revoked',
                 'final_revalidation_failure', 'no_eye')
        with tempfile.TemporaryDirectory() as tmp:
            for mode, name in enumerate(modes):
                with self.subTest(mode=name):
                    binary = Path(tmp) / f'{mode}.vvp'
                    build = subprocess.run([
                        'iverilog', '-g2012', '-Wall', '-s', 'tb_rx_training_v3',
                        f'-Ptb_rx_training_v3.MODE={mode}', '-o', str(binary),
                        *map(str, sorted((ROOT / 'rtl/v2').glob('*.v'))),
                        str(ROOT / 'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                        str(ROOT / 'tb/tb_dcc_release_v2.v'),
                        str(ROOT / 'tb/tb_rx_training_v3.v')], capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertIn('PASS v3', run.stdout)

    def test_warmup_loss_bound_at_all_clock_phases_and_supported_frequencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mhz in (390, 400, 410):
                with self.subTest(mhz=mhz):
                    binary = Path(tmp) / f'loss-{mhz}.vvp'
                    build = subprocess.run([
                        'iverilog', '-g2012', '-Wall', '-s', 'tb_rx_clock_loss_v3',
                        f'-Ptb_rx_clock_loss_v3.HALF_PERIOD={500 / mhz:.12f}', '-o', str(binary),
                        *map(str, sorted((ROOT / 'rtl/v2').glob('*.v'))),
                        str(ROOT / 'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                        str(ROOT / 'tb/tb_dcc_release_v2.v'),
                        str(ROOT / 'tb/tb_rx_clock_loss_v3.v')], capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertIn('PASS v3', run.stdout)
