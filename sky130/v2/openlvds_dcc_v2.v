// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Source candidate for Chen et al. Fig.10(a). Native feasibility and physical
// qualification are mandatory; do not substitute ideal delays for these cells.
module openlvds_rising_pulse_v2 #(parameter RESET_BUFFERS=2)(
    input wire phase, reset_n, output wire pulse
);
    wire delayed, pulse_n, clear_n;
    wire [RESET_BUFFERS:0] chain;
    assign chain[0] = pulse;
    genvar i;
    generate for (i=0; i<RESET_BUFFERS; i=i+1) begin: reset_delay
        (* keep="true", dont_touch="true" *)
        sky130_fd_sc_hd__buf_1 reset_buffer(.A(chain[i]), .X(chain[i+1]));
    end endgenerate
    assign delayed = chain[RESET_BUFFERS];
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_1 pulse_invert(.A(delayed), .Y(pulse_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 pulse_clear(.A(reset_n), .B(pulse_n), .X(clear_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 pulse_ff(.CLK(phase), .D(1'b1), .RESET_B(clear_n), .Q(pulse));
endmodule

module openlvds_dcc_v2 #(parameter RESET_BUFFERS=2)(
    input wire phase0, phase180, reset_n, output wire clock_out
);
    wire a, b, events, feedback;
    (* keep_hierarchy="yes", dont_touch="true" *)
    openlvds_rising_pulse_v2 #(.RESET_BUFFERS(RESET_BUFFERS)) first(.phase(phase0), .reset_n(reset_n), .pulse(a));
    (* keep_hierarchy="yes", dont_touch="true" *)
    openlvds_rising_pulse_v2 #(.RESET_BUFFERS(RESET_BUFFERS)) second(.phase(phase180), .reset_n(reset_n), .pulse(b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__or2_1 combine(.A(a), .B(b), .X(events));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_1 toggle_feedback(.A(clock_out), .Y(feedback));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 toggle_ff(.CLK(events), .D(feedback), .RESET_B(reset_n), .Q(clock_out));
endmodule
`default_nettype wire
