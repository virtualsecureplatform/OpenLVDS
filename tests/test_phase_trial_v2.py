# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class PhaseTrialTests(unittest.TestCase):
    def run_model(self,admitted):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            build=subprocess.run(['iverilog','-g2012','-Wall','-s','tb_phase_trial_v2',
                '-Ptb_phase_trial_v2.ADMITTED='+str(admitted),'-o',str(binary),
                *map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(ROOT/'tb/tb_phase_trial_v2.v')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)

    def test_real_launcher_and_retained_events_reject_missing_duplicate_and_aliased_epochs(self):
        self.run_model(1)

    def test_default_unadmitted_model_never_launches_or_grants_valid_measurement(self):
        self.run_model(0)
