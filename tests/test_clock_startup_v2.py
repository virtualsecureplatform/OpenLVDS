# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import clocking_v2


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class ClockStartupTests(unittest.TestCase):
    def run_tb(self,**parameters):
        with tempfile.TemporaryDirectory() as tmp:
            top='tb_clock_startup_v2';binary=Path(tmp)/'test.vvp'
            compile=subprocess.run(['iverilog','-g2012','-Wall','-s',top,
                *['-P'+top+'.'+name+'='+str(value) for name,value in parameters.items()],'-o',str(binary),
                *map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                # Existing explicit test-cell models; its old test top is not elaborated.
                str(ROOT/'tb/tb_dcc_release_v2.v'),str(ROOT/'tb/tb_clock_startup_v2.v')],capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stdout+compile.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)
            return run.stdout

    def test_actual_dcc_topology_warmup_cdc_loss_and_reference_training_stream(self):
        output=self.run_tb()
        rows=re.findall(r'PAIR\s+(\d+) ([01]{2}) ([01])',output)
        self.assertEqual(len(rows),432)
        serial=''.join(r[1] for r in rows)
        frame=''.join(map(str,clocking_v2.training_frame()))
        self.assertEqual(serial,frame*3+format(clocking_v2.END_MARKER,'032b')+'10'*32)
        self.assertEqual([r[2] for r in rows],['0']*400+['1']*32)

    def test_dcc_model_admission_is_closed_by_default(self):self.run_tb(ADMITTED=0)
    def test_shortened_hardware_warmup_is_rejected(self):self.run_tb(WARMUP=255)
    def test_both_absent_delivered_clocks_time_out(self):self.run_tb(MISSING_CLOCK=1)
    def test_one_warm_phase_cannot_qualify_missing_other_phase(self):self.run_tb(MISSING_CLOCK=2)
