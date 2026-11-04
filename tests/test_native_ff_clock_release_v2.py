# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_ff_clock_release_v2 as release


class NativeFfReleaseTests(unittest.TestCase):
    def test_both_native_ff_resets_clear_from_request_and_second_data_uses_first_q(self):
        for drive in [1,2]:
            a,b=release.gates(drive)
            self.assertEqual(a[2]['RESET_B'],'REQUEST');self.assertEqual(b[2]['RESET_B'],'REQUEST')
            self.assertEqual(b[2]['D'],a[2]['Q']);self.assertEqual(a[2]['D'],'REQUEST')
            self.assertEqual(a[1],f'dfrtp_{drive}');self.assertEqual(b[1],f'dfrtp_{drive}')

    def test_keeps_native_private_nodes_and_actual_extracted_output_buffer(self):
        library='.subckt sky130_fd_sc_hd__dfrtp_1 CLK D RESET_B VGND VNB VPB VPWR Q\nX0 Q CLK private VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        rc={release.components.CLOCK_BUFFER:dict(info=dict(ports=['A','X','VGND','VPWR']))}
        text=release.source(1,library,rc)
        self.assertIn('r0__private',text);self.assertIn('r1__private',text)
        self.assertIn('Xready_buffer ready1 RESET_N VGND VPWR '+release.components.CLOCK_BUFFER,text)
        self.assertNotIn('.ic',text);self.assertNotIn('BRESET',text)


if __name__=='__main__':unittest.main()
