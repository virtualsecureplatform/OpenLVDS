// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Candidate corresponding to the native dfrtp_1 + inv_4 output experiment.
// Inverting the Q output cancels part of CQ rise/fall asymmetry. This remains
// a source candidate until physical RC and all-PVT/load qualification pass.
// Output is HIGH while reset is asserted; callers must invalidate downstream
// state during reset/calibration. Its first phase0 event produces a falling
// edge. Both quadrature DCCs must use this same polarity convention.
module openlvds_dcc_output_v2 (
    input wire phase0, phase180, reset_n, output wire clock_out
);
    wire a,b,events,raw_q,feedback;
    (* keep_hierarchy="yes", dont_touch="true" *)
    openlvds_rising_pulse_v2 #(.RESET_BUFFERS(0)) first(.phase(phase0),.reset_n(reset_n),.pulse(a));
    (* keep_hierarchy="yes", dont_touch="true" *)
    openlvds_rising_pulse_v2 #(.RESET_BUFFERS(0)) second(.phase(phase180),.reset_n(reset_n),.pulse(b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__or2_1 combine(.A(a),.B(b),.X(events));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_1 toggle_feedback(.A(raw_q),.Y(feedback));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 toggle_ff(.CLK(events),.D(feedback),.RESET_B(reset_n),.Q(raw_q));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 output_drive(.A(raw_q),.Y(clock_out));
endmodule
`default_nettype wire
