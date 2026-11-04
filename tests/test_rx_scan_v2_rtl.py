# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from clocking_v2 import Delay,select_eye
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh for RTL checks')
class RXScanRTLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.binary=cls.root/'scan.vvp'
        subprocess.run(['iverilog','-g2012','-Wall','-s','tb_rx_scan_v2','-o',str(cls.binary),
            str(ROOT/'rtl/v2/openlvds_rx_scan_v2.v'),str(ROOT/'tb/tb_rx_scan_v2.v')],check=True,capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_case(self,positions,passed,mode=0,expected_reason=0,corrupt=False):
        table=[Delay(i,p,p+1) for i,p in enumerate(positions)]
        self.assertEqual(len(table),101)
        if expected_reason==0:
            expected=select_eye(table,passed)
        else:expected=dict(code=0,clearance_ps=0)
        lines=[]
        for i,d in enumerate(table):
            hi=d.hi_ps if not corrupt or i!=1 else d.lo_ps+50
            lines.append(f'{(int(passed[i])<<32)|(hi<<16)|d.lo_ps:09x}')
        path=self.root/'rom.hex';path.write_text('\n'.join(lines)+'\n')
        result=subprocess.run(['vvp',str(self.binary),f'+ROM={path}',f'+MODE={mode}',
            f'+EXPECT_CODE={expected["code"]}',f'+EXPECT_REASON={expected_reason}',
            f'+EXPECT_CLEARANCE={expected["clearance_ps"]}'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS v2',result.stdout)
    def test_unequal_code_spacing_matches_physical_reference(self):
        positions=list(range(0,300,5))+list(range(300,901,15))
        self.run_case(positions,[True]*101)
    def test_eyes_and_missing_markers_do_not_bridge_islands(self):
        positions=[i*10 for i in range(101)]
        for passed in [[i>=20 for i in range(101)], [i<10 or i>=30 for i in range(101)],
                       [i<40 or i>60 for i in range(101)]]:
            try:select_eye([Delay(i,p,p+1) for i,p in enumerate(positions)],passed)
            except ValueError:reason=6
            else:reason=0
            self.run_case(positions,passed,expected_reason=reason)
    def test_final_revalidation_and_faults(self):
        positions=[i*10 for i in range(101)]
        for mode,reason in [(2,7),(4,6),(5,1),(6,4),(8,2)]:
            self.run_case(positions,[True]*101,mode=mode,expected_reason=reason)
    def test_bad_delay_rom_cannot_authorize_training(self):
        self.run_case([i*10 for i in range(101)],[True]*101,expected_reason=8,corrupt=True)
