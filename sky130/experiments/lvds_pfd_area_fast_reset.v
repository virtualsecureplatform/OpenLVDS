// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module lvds_pfd(
`ifdef USE_POWER_PINS
    inout wire VPWR, inout wire VGND,
`endif
    input wire REF, input wire FB, input wire RESET_N, input wire PD_ENABLE,
    output wire UP, output wire DN
);
    wire disallow,clear_b,logic1,logic0,raw_up,raw_dn;
    sky130_fd_sc_hd__conb_1 tie(.HI(logic1),.LO(logic0));
    sky130_fd_sc_hd__nand2_1 reset_disable(.A(RESET_N),.B(PD_ENABLE),.Y(disallow));
    // clear_b = !(raw_up & raw_dn | disallow): one gate on the reset path.
    sky130_fd_sc_hd__a22oi_4 clear(.A1(raw_up),.A2(raw_dn),.B1(disallow),.B2(logic1),.Y(clear_b));
    sky130_fd_sc_hd__dfrtp_4 ref_ff(.CLK(REF),.D(logic1),.RESET_B(clear_b),.Q(raw_up));
    sky130_fd_sc_hd__dfrtp_4 fb_ff(.CLK(FB),.D(logic1),.RESET_B(clear_b),.Q(raw_dn));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 up_drive(.A(raw_up),.X(UP));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 dn_drive(.A(raw_dn),.X(DN));
endmodule
`default_nettype wire
