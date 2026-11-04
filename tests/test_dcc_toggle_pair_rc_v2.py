# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_toggle_pair_rc_v2 as pilot


class NativeToggleFixtureTests(unittest.TestCase):
    def test_only_the_native_top_instance_is_adapted_and_all_mos_terminals_retained(self):
        spec=dict(variant='native',process='ss',temperature=40,mhz=410,load_ff=100,slew0_ps=100,slew180_ps=100,duty=.7)
        info=dict(ports=['VGND','VPWR','clock_out','phase0','phase180','reset_n'])
        text='.subckt '+pilot.NAME+' '+' '.join(info['ports'])+'\nX0 clock_out phase0 private VGND sky130_fd_pr__nfet_01v8 w=.36 l=.15\n.ends\n'
        with patch.dict(os.environ,PDK_ROOT='/pdk'):deck=pilot.fixture(Path('/pilot'),spec,info,text)
        self.assertIn('XD 0 VDD Q P0 P180 RESET_N '+pilot.NAME+'\n',deck)
        self.assertIn('.include "/pilot/native.spice"',deck)
        self.assertIn('V(XD:private)',deck)
        self.assertNotIn('combine.X',deck)
        self.assertIn('CQ Q 0 100f',deck)


if __name__=='__main__':unittest.main()
