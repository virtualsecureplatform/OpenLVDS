# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from physical_policy import delay_cells_absent,pfd_paths_retained


class PhysicalPolicy(unittest.TestCase):
    direct='''module lvds_pfd();
sky130_fd_sc_hd__dfrtp_4 ref_ff (.CLK(REF), .D(one), .RESET_B(clear_b), .Q(raw_up));
sky130_fd_sc_hd__dfrtp_4 fb_ff (.CLK(FB), .D(one), .RESET_B(clear_b), .Q(raw_dn));
sky130_fd_sc_hd__buf_8 up_drive (.A(raw_up), .X(UP));
sky130_fd_sc_hd__buf_8 dn_drive (.A(raw_dn), .X(DN));
sky130_fd_sc_hd__and2_4 coincidence (.A(UP), .B(DN), .X(both));
sky130_fd_sc_hd__buf_8 qual_ref (.A(QREF), .X(qr));
sky130_fd_sc_hd__buf_8 qual_fb (.A(QFB), .X(qf));
sky130_fd_sc_hd__buf_8 qual_window_first (.A(QWIN), .X(qwm));
sky130_fd_sc_hd__buf_8 qual_window_second (.A(qwm), .X(qw));
sky130_fd_sc_hd__inv_4 qual_ref_inv (.A(qr), .Y(qr_b));
sky130_fd_sc_hd__inv_4 qual_fb_inv (.A(qf), .Y(qf_b));
sky130_fd_sc_hd__a22oi_4 qual_compare (.A1(qr), .A2(qf_b), .B1(qf), .B2(qr_b), .Y(error_n));
sky130_fd_sc_hd__inv_16 qual_error_drive (.A(error_n), .Y(error_raw));
sky130_fd_sc_hd__and2_4 qual_mask (.A(error_raw), .B(qw), .X(ERR));
endmodule'''

    def test_canonical_native_pfd_retains_all_paths(self):
        source=Path(__file__).resolve().parents[1]/'sky130/lvds_pfd.v'
        self.assertTrue(pfd_paths_retained(source.read_text()))

    def test_direct_detector_interface_is_accepted(self):
        self.assertTrue(pfd_paths_retained(self.direct))
        self.assertTrue(delay_cells_absent(self.direct))

    def test_inserted_delay_cell_is_rejected(self):
        buffered=self.direct.replace('.CLK(REF)','.CLK(net3)')
        buffered+='\nsky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(REF), .X(net3));\n'
        self.assertFalse(pfd_paths_retained(buffered))
        self.assertFalse(delay_cells_absent(buffered))

    def test_ordinary_output_buffer_also_breaks_direct_pfd_interface(self):
        buffered=self.direct.replace('.Q(raw_up)','.Q(net7)')
        buffered+='\nsky130_fd_sc_hd__buf_4 output7 (.A(net7), .X(UP));\n'
        self.assertTrue(delay_cells_absent(buffered))
        self.assertFalse(pfd_paths_retained(buffered))

    def test_unbuffered_reset_coincidence_is_rejected(self):
        self.assertFalse(pfd_paths_retained(self.direct.replace('.A(UP), .B(DN)', '.A(raw_up), .B(raw_dn)')))

    def test_asymmetric_drive_strength_is_rejected(self):
        self.assertFalse(pfd_paths_retained(self.direct.replace('buf_8 dn_drive','buf_4 dn_drive')))


    def test_qualification_bypasses_are_rejected(self):
        for old,new in [('.A(QREF)','.A(UP)'),('.A(QFB)','.A(DN)'),
                        ('.A(QWIN)','.A(REF)'),('.A(qwm)','.A(QWIN)'),
                        ('.A2(qf_b)','.A2(qf)'),('.B2(qr_b)','.B2(qr)'),
                        ('.B(qw)','.B(qwm)'),('inv_16 qual_error_drive','inv_4 qual_error_drive'),
                        ('.X(qf)','.X(qr)'),('.X(ERR)','.X(unused)')]:
            with self.subTest(change=(old,new)):
                self.assertFalse(pfd_paths_retained(self.direct.replace(old,new)))


if __name__=='__main__':unittest.main()
