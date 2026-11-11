// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// SF source traces proved the old self-reset FF can retrigger while CLK is
// HIGH. Local RESET_B now latches LOW after the pulse and can rearm only when
// CLK falls: H = RESET_N & (!CLK | (!Q & H)). Native qualification is required.
module openlvds_dcc_inv6_300 (
`ifdef USE_POWER_PINS
    inout wire VPWR,VGND,
`endif
    input wire phase0,phase180,reset_n,output wire clock_out
);
    wire high,low,a,b,aclk_n,bclk_n,qa_n,qb_n,aclear_n,bclear_n,areset,breset;
    wire events,raw_q,feedback;
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__conb_1 tie(.HI(high),.LO(low));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__dfrtp_1 first_ff(.CLK(phase0),.D(high),.RESET_B(areset),.Q(a));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_1 first_phase_inverse(.A(phase0),.Y(aclk_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_1 first_pulse_inverse(.A(a),.Y(qa_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__a21oi_1 first_hold(.A1(qa_n),.A2(areset),.B1(aclk_n),.Y(aclear_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__and2b_1 first_clear(.A_N(aclear_n),.B(reset_n),.X(areset));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__dfrtp_1 second_ff(.CLK(phase180),.D(high),.RESET_B(breset),.Q(b));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_1 second_phase_inverse(.A(phase180),.Y(bclk_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_1 second_pulse_inverse(.A(b),.Y(qb_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__a21oi_1 second_hold(.A1(qb_n),.A2(breset),.B1(bclk_n),.Y(bclear_n));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__and2b_1 second_clear(.A_N(bclear_n),.B(reset_n),.X(breset));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__or2_1 combine(.A(a),.B(b),.X(events));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_1 toggle_feedback(.A(raw_q),.Y(feedback));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__dfrtp_1 toggle_ff(.CLK(events),.D(feedback),.RESET_B(reset_n),.Q(raw_q));
    (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__inv_6 output_drive(.A(raw_q),.Y(clock_out));
endmodule
`default_nettype wire
