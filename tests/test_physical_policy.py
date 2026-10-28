# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from physical_policy import delay_cells_absent,pfd_ports_direct


class PhysicalPolicy(unittest.TestCase):
    direct='''module lvds_pfd();
sky130_fd_sc_hd__dfrtp_4 ref_ff (.CLK(REF), .D(one), .RESET_B(clear_b), .Q(UP));
sky130_fd_sc_hd__dfrtp_4 fb_ff (.CLK(FB), .D(one), .RESET_B(clear_b), .Q(DN));
endmodule'''

    def test_direct_detector_interface_is_accepted(self):
        self.assertTrue(pfd_ports_direct(self.direct))
        self.assertTrue(delay_cells_absent(self.direct))

    def test_inserted_delay_cell_is_rejected(self):
        buffered=self.direct.replace('.CLK(REF)','.CLK(net3)')
        buffered+='\nsky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(REF), .X(net3));\n'
        self.assertFalse(pfd_ports_direct(buffered))
        self.assertFalse(delay_cells_absent(buffered))

    def test_ordinary_output_buffer_also_breaks_direct_pfd_interface(self):
        buffered=self.direct.replace('.Q(UP)','.Q(net7)')
        buffered+='\nsky130_fd_sc_hd__buf_4 output7 (.A(net7), .X(UP));\n'
        self.assertTrue(delay_cells_absent(buffered))
        self.assertFalse(pfd_ports_direct(buffered))


if __name__=='__main__':unittest.main()
