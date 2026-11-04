# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_clock_hold_v2 as hold
import test_digital_dcc_v2 as source_fixture
ROOT=Path(__file__).resolve().parents[1]

class ClockHoldTests(unittest.TestCase):
    def wave(self,extra=False):
        names,w=source_fixture.DCCMeasurementTests().wave();t=w[:,0]*1e12
        for channel,edges in [('a',2000+np.arange(19)*2500),('b',3250+np.arange(19)*2500)]:
            reset=w[:,names.index('v(xd.'+channel+'reset)')];reset[:]=1.8
            for edge in edges:reset[(t>=edge+100)&(t<edge+850)]=0
        if extra:w[(t>=12400)&(t<12450),names.index('v(xd.a)')]=1.8
        return names,w
    def test_profile_does_not_recurse_and_one_pulse_hold_is_required(self):
        for extra in [False,True]:
            with patch.object(hold.base,'read_raw',return_value=self.wave(extra)),hold.profile():
                result=hold.base.measure(Path('/fixture'),dict(mhz=400,phase_error_ps=0))
            self.assertEqual(result['pulse_generator_integrity_passed'],not extra)
            self.assertFalse(result['qualified_phy'])
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
    def test_native_failure_mode_logic_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            result=subprocess.run(['iverilog','-g2012','-s','tb_dcc_clock_hold_v2','-o',str(binary),
                str(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v'),str(ROOT/'tb/tb_dcc_clock_hold_v2.v')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)
