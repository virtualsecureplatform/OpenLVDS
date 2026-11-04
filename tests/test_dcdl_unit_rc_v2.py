# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_unit_rc_v2 as hybrid
import probe_dcdl_node_bank_pvt_v2 as source


class HybridUnitRCTests(unittest.TestCase):
    def test_source_devices_are_replaced_once_without_dropping_the_node_shunt(self):
        text,_=source.circuit(0,4);modified=hybrid.bank(text)
        self.assertNotIn('XSWN0 ',modified)
        self.assertEqual(modified.count('openlvds_mim_switch_unit_v2'),31)
        self.assertIn('XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w=4 l=4',modified)
        for i in range(31):self.assertIn(f'XU{i} r0 E{i} EB{i} VDD VSS',modified)

    def test_actual_extracted_terminal_probes_and_internal_shunts_are_not_duplicated(self):
        primitive=('X0 NODE.t0 ENB.t2 CAP.t1 VDD.t0 sky130_fd_pr__pfet_01v8 w=.84 l=.15\n'
            'X3 CAP.t2 EN.t0 NODE.t1 VSS.t4 sky130_fd_pr__nfet_01v8 w=.42 l=.15\n'
            'X4 VSS.t2 ENB.t1 CAP.t0 VSS.t1 sky130_fd_pr__nfet_01v8 w=.42 l=.15\n')
        devices=hybrid.devices(primitive)
        self.assertEqual(len(devices),93)
        spec=dict(process='ss',temperature=40,coarse=0,codes=[0,31,0],restore='mim2x2',control_slew_ps=20)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            text=hybrid.fixture(Path('/context'),spec,devices)
        self.assertNotIn('XCEB',text);self.assertNotIn('V(XD:cap0)',text)
        self.assertIn('V(XD:XU0:NODE.t0)',text);self.assertIn('V(XD:XU30:VSS.t4)',text)
        self.assertIn('/unit_rc.spice"',text)
