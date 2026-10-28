// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module lvds_pfd(
`ifdef USE_POWER_PINS
    inout wire VPWR, inout wire VGND,
`endif
    input wire REF, input wire FB, input wire RESET_N, input wire PD_ENABLE,
    output wire UP, output wire DN, output wire ERR
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
    sky130_fd_sc_hd__xor2_1 error_width(.A(UP),.B(DN),.X(ERR));
endmodule
`default_nettype wire
