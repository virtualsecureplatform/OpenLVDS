# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Use scripts/env.sh')
class RXDeskewTransactionTests(unittest.TestCase):
    def test_composed_safe_updates_settling_warmup_and_failures(self):
        modes = ('two_updates', 'withheld_grant', 'wrong_settle_tag',
                 'stale_matching_settle', 'source_loss', 'unadmitted_dcc',
                 'unadmitted_transaction', 'cancel_retains_word', 'stale_clock_ready',
                 'missing_physical_settling', 'cancel_after_physical_commit',
                 'low_only_before_commit')
        with tempfile.TemporaryDirectory() as tmp:
            for mode, name in enumerate(modes):
                with self.subTest(mode=name):
                    binary = Path(tmp) / f'{mode}.vvp'
                    build = subprocess.run([
                        'iverilog', '-g2012', '-Wall', '-s', 'tb_rx_deskew_transaction_v2',
                        f'-Ptb_rx_deskew_transaction_v2.MODE={mode}', '-o', str(binary),
                        *map(str, sorted((ROOT / 'rtl/v2').glob('*.v'))),
                        str(ROOT / 'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                        str(ROOT / 'tb/tb_dcc_release_v2.v'),
                        str(ROOT / 'tb/tb_rx_deskew_transaction_v2.v')], capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertIn('PASS v2', run.stdout)
