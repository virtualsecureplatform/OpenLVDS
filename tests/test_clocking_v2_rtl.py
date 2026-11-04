# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Use scripts/env.sh for RTL checks')
class V2RTLTests(unittest.TestCase):
    def run_tb(self, name):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'test.vvp'
            subprocess.run(['iverilog','-g2012','-Wall','-s',name,'-o',str(out),
                *map(str, sorted((ROOT/'rtl/v2').glob('*.v'))),
                *([str(ROOT/'sky130/v2/openlvds_dcdl_v2.v')] if name=='tb_dcdl_v2' else []),
                str(ROOT/'tb'/f'{name}.v')],check=True,capture_output=True,text=True)
            result=subprocess.run(['vvp',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS v2',result.stdout)
            return result.stdout

    def test_calibration_management_faults(self): self.run_tb('tb_clocking_control_v2')
    def test_atomic_code_commit(self): self.run_tb('tb_code_mailbox_v2')

    def test_training_rotations_and_payload_boundary(self): self.run_tb("tb_training_v2")

    def test_transmitted_frame_matches_independent_reference(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import clocking_v2
        output=self.run_tb('tb_training_tx_v2')
        rows=re.findall(r'PAIR\s+(\d+) ([01]{2}) ([01])',output)
        self.assertEqual(len(rows),432)
        serial=''.join(r[1] for r in rows)
        frame=''.join(map(str,clocking_v2.training_frame()))
        self.assertEqual(serial,frame*3+format(clocking_v2.END_MARKER,'032b')+'10'*32)
        self.assertEqual([r[2] for r in rows],['0']*400+['1']*32)

    def test_dcdl_source_topology_and_polarity(self): self.run_tb("tb_dcdl_v2")
