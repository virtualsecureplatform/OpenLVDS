# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_toggle_pair_v2 as pair
import probe_dcc_toggle_pair_v3 as gated
import test_dcc_native_rc_v2 as native_fixture


class TogglePairPilotTests(unittest.TestCase):
    def test_native_source_cells_are_inlined_without_ideal_timing_or_node_aliases(self):
        library=''
        for name,ports in [('dfrtp_1','CLK D RESET_B VGND VNB VPB VPWR Q'),
                           ('inv_1','A VGND VNB VPB VPWR Y'),('xnor2_4','A B VGND VNB VPB VPWR Y')]:
            nodes='Q D CLK RESET_B' if name=='dfrtp_1' else 'Y A private VGND'
            library+=f'.subckt sky130_fd_sc_hd__{name} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.36 l=.15\n.ends sky130_fd_sc_hd__{name}\n'
        source=pair.source_pair(1,library)
        self.assertIn('Xaff__X0 a an phase0 reset_n sky130_fd_pr__nfet_01v8 w=.36 l=.15',source)
        self.assertIn('Xbff__X0 b bn phase180 reset_n',source)
        self.assertIn('Xainv__X0 an a ainv__private VGND',source)
        self.assertIn('Xbinv__X0 bn b binv__private VGND',source)
        self.assertIn('Xcombine__X0 clock_out a combine__private VGND',source)
        self.assertEqual(len(pair.native.terminals(source)),5)
        with self.assertRaisesRegex(ValueError,'Undeclared'):pair.source_pair(4,library)

    def test_alternative_measurement_rejects_missing_or_inverted_output_events(self):
        fixture=native_fixture.NativeDccPilotTests()
        for options,expected in [({},True),({'missing':True},False),({'complement':True},False),({'overstress':True},False)]:
            with patch.object(pair,'read_raw',return_value=fixture.wave(**options)):
                result=pair.measure(Path('/fixture'),fixture.spec,fixture.info,fixture.text)
            self.assertEqual(result['pilot_passed'],expected)
            self.assertFalse(result['qualified_phy'])

    def test_reset_qualified_feedback_replaces_both_unconditional_inverters(self):
        library=''
        for name,ports,nodes in [
            ('dfrtp_1','CLK D RESET_B VGND VNB VPB VPWR Q','Q D CLK RESET_B'),
            ('and2b_1','A_N B VGND VNB VPB VPWR X','X A_N B VGND'),
            ('xnor2_4','A B VGND VNB VPB VPWR Y','Y A B VGND')]:
            library+=f'.subckt sky130_fd_sc_hd__{name} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.36 l=.15\n.ends sky130_fd_sc_hd__{name}\n'
        source=gated.source_pair(1,library)
        self.assertIn('Xafeedback__X0 an a reset_n VGND',source)
        self.assertIn('Xbfeedback__X0 bn b reset_n VGND',source)
        self.assertIn('Xaff__X0 a an phase0 reset_n',source)
        self.assertIn('Xbff__X0 b bn phase180 reset_n',source)
        self.assertNotIn('ainv',source)
        self.assertEqual(len(gated.native.terminals(source)),5)


if __name__=='__main__':unittest.main()
