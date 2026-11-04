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
class TXControlTests(unittest.TestCase):
    def run_tb(self,top,**parameters):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            build=subprocess.run(['iverilog','-g2012','-Wall','-s',top,
                *['-P'+top+'.'+name+'='+str(value) for name,value in parameters.items()],'-o',str(binary),
                *map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                str(ROOT/'tb/tb_dcc_release_v2.v'),str(ROOT/'tb'/f'{top}.v')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)
            return run.stdout

    def test_single_deadline_stage_failures_and_retraining_protocol(self):self.run_tb('tb_clock_sequence_v2')
    def test_invalid_timeout_is_rejected(self):self.run_tb('tb_clock_sequence_v2',LIMIT=0)

    def test_composed_tx_calibrates_warms_and_transmits_the_independent_frame(self):
        output=self.run_tb('tb_tx_control_v2')
        rows=re.findall(r'PAIR\s+(\d+) ([01]{2}) ([01])',output)
        self.assertEqual(len(rows),432)
        frame=''.join(map(str,clocking_v2.training_frame()))
        self.assertEqual(''.join(r[1] for r in rows),frame*3+format(clocking_v2.END_MARKER,'032b')+'10'*32)
        self.assertEqual([r[2] for r in rows],['0']*400+['1']*32)

    def test_unadmitted_dll_model_cannot_release_tx(self):self.run_tb('tb_tx_control_v2',DLL_ADMITTED=0)
    def test_unadmitted_dcc_model_cannot_release_tx(self):self.run_tb('tb_tx_control_v2',DCC_ADMITTED=0)
    def test_missing_configuration_settling_obeys_the_overall_deadline(self):self.run_tb('tb_tx_control_v2',HOLD_SETTLE=1)
