# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class TaggedLaunchTests(unittest.TestCase):
    def test_single_pulses_and_unwrapped_reference_across_frequency_duty_and_cdc(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            build=subprocess.run(['iverilog','-g2012','-Wall','-s','tb_tag_launch_v2','-o',str(binary),
                str(ROOT/'rtl/v2/openlvds_code_mailbox_v2.v'),str(ROOT/'rtl/v2/openlvds_tag_launch_v2.v'),
                str(ROOT/'tb/tb_tag_launch_v2.v')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)
