# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dcc_physical_policy_v2 import interface_retained
ROOT=Path(__file__).resolve().parents[1]

class DCCPhysicalTopologyTests(unittest.TestCase):
    def test_tie_reset_event_and_output_paths_are_structural_requirements(self):
        source=(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v').read_text()
        self.assertTrue(interface_retained(source))
        variants=[source.replace('.D(high)','.D(low)',1),
            source.replace('.CLK(phase0)','.CLK(phase180)',1),
            source.replace('.A2(areset)','.A2(breset)',1),
            source.replace('.CLK(events)','.CLK(phase0)',1),
            source.replace('sky130_fd_sc_hd__inv_4 output_drive','sky130_fd_sc_hd__inv_1 output_drive'),
            source.replace('.A(a),.B(b)','.A(b),.B(a)')]
        for changed in variants:self.assertFalse(interface_retained(changed))
    def test_new_signal_cells_cannot_hide_in_placement_repair(self):
        source=(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v').read_text()
        self.assertFalse(interface_retained(source+'\nsky130_fd_sc_hd__buf_1 extra(.A(events),.X(new_events));'))
        self.assertTrue(interface_retained(source+'\nsky130_fd_sc_hd__fill_1 filler();'))
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
    def test_reset_phase_alignment_for_both_dccs(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            result=subprocess.run(['iverilog','-g2012','-s','tb_dcc_release_v2','-o',str(binary),
                str(ROOT/'rtl/v2/openlvds_dcc_release_v2.v'),str(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                str(ROOT/'tb/tb_dcc_release_v2.v')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS v2',run.stdout)
