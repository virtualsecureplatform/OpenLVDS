// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module lvds_pfd(
`ifdef USE_POWER_PINS
    inout wire VPWR, inout wire VGND,
`endif
    input wire REF, input wire FB, input wire RESET_N, input wire PD_ENABLE,
    output wire UP, output wire DN, output wire ERR,
    input wire QREF, input wire QFB, input wire QWIN
);
    wire allow,both,clear_b,logic1,logic0,raw_up,raw_dn;
    sky130_fd_sc_hd__conb_1 tie(.HI(logic1),.LO(logic0));
    sky130_fd_sc_hd__and2_1 ena(.A(RESET_N),.B(PD_ENABLE),.X(allow));
    sky130_fd_sc_hd__and2_4 coincidence(.A(UP),.B(DN),.X(both));
    sky130_fd_sc_hd__and2b_4 clear(.A_N(both),.B(allow),.X(clear_b));
    sky130_fd_sc_hd__dfrtp_4 ref_ff(.CLK(REF),.D(logic1),.RESET_B(clear_b),.Q(raw_up));
    sky130_fd_sc_hd__dfrtp_4 fb_ff(.CLK(FB),.D(logic1),.RESET_B(clear_b),.Q(raw_dn));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 up_drive(.A(raw_up),.X(UP));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 dn_drive(.A(raw_dn),.X(DN));
    // Restore the matched RC sense paths, then qualify only the rising window.
    // The PFD's reset coincidence pulse is absent from this raw-clock measure.
    wire qr,qf,qwm,qw,qr_b,qf_b,error_n,error_raw;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 qual_ref(.A(QREF),.X(qr));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 qual_fb(.A(QFB),.X(qf));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 qual_window_first(.A(QWIN),.X(qwm));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 qual_window_second(.A(qwm),.X(qw));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 qual_ref_inv(.A(qr),.Y(qr_b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 qual_fb_inv(.A(qf),.Y(qf_b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__a22oi_4 qual_compare(.A1(qr),.A2(qf_b),.B1(qf),.B2(qr_b),.Y(error_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_16 qual_error_drive(.A(error_n),.Y(error_raw));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_4 qual_mask(.A(error_raw),.B(qw),.X(ERR));
endmodule
`default_nettype wire
