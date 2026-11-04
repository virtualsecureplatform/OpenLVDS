# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class DLLMeasurementTests(unittest.TestCase):
    def run_model(self,integrated=0,admitted=1,composed=False):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            top='tb_dll_measurement_v2' if composed else 'tb_dll_measure_v2'
            parameters=['-P'+top+'.ADMITTED='+str(admitted)]
            if not composed:parameters+=['-P'+top+'.INTEGRATED='+str(integrated)]
            build=subprocess.run(['iverilog','-g2012','-Wall','-s',top,*parameters,
                '-o',str(binary),*map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),
                str(ROOT/'tb'/f'{top}.v')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)

    def test_pairwise_brackets_votes_swaps_retry_and_generation_faults(self):self.run_model()
    def test_real_calibration_converges_requires_64_confirmations_and_freezes(self):self.run_model(integrated=1)
    def test_default_model_admission_is_closed(self):self.run_model(admitted=0)
    def test_composed_launcher_trial_and_measurement_engine(self):self.run_model(composed=True)
    def test_composed_physical_interface_defaults_closed(self):self.run_model(composed=True,admitted=0)
