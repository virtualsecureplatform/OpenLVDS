// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Experimental reset-qualified two-toggle DCC. No physical/timing admission.
// Qualifying feedback with reset prevents a stored master-latch 1 from
// propagating when async reset is released during the clock HIGH interval.
module openlvds_dcc_toggle_pair_v2 (
`ifdef USE_POWER_PINS
    inout wire VPWR,VGND,
`endif
    input wire phase0,phase180,reset_n,output wire clock_out
);
    wire a,b,an,bn;
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__and2b_1 first_feedback(.A_N(a),.B(reset_n),.X(an));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__and2b_1 second_feedback(.A_N(b),.B(reset_n),.X(bn));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__dfrtp_2 first_ff(.CLK(phase0),.D(an),.RESET_B(reset_n),.Q(a));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__dfrtp_2 second_ff(.CLK(phase180),.D(bn),.RESET_B(reset_n),.Q(b));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__xnor2_4 combine(.A(a),.B(b),.Y(clock_out));
endmodule
`default_nettype wire
