# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class DLLControlTests(unittest.TestCase):
    def run_tb(self,top,admitted=None,**overrides):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            parameters=[] if admitted is None else ['-P'+top+'.ADMITTED='+str(admitted)]
            parameters+=['-P'+top+'.'+name+'='+str(value) for name,value in overrides.items()]
            compile=subprocess.run(['iverilog','-g2012','-Wall','-s',top,*parameters,'-o',str(binary),
                *map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(ROOT/'tb'/f'{top}.v')],capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stdout+compile.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)

    def test_atomic_mode_codes_physical_settle_stale_generation_retrain_and_freeze(self):self.run_tb('tb_dll_configuration_v2')
    def test_complete_controller_converges_64_times_through_actual_isolated_trials(self):self.run_tb('tb_dll_control_v2',1)
    def test_unadmitted_physical_model_cannot_launch_or_lock(self):self.run_tb('tb_dll_control_v2',0)
    def test_clock_loss_bound_includes_cdc_and_registered_consumer(self):
        for mhz in [390,400,410]:
            with self.subTest(mhz=mhz):self.run_tb('tb_clock_watch_bound_v2',RAW_HALF_NS=500/mhz)
    def test_missing_physical_settling_times_out_without_launch(self):self.run_tb('tb_dll_control_v2',1,HOLD_SETTLE=1)
