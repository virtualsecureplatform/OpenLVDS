// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_dll_control #(
    parameter integer GOOD_CYCLES=64,
    parameter integer STARTUP_CYCLES=32
) (
    input wire clk, input wire reset_n, input wire clock_ready,
    input wire phase_bad,
    output reg pd_enable, output reg locked
);
    wire control_reset_n=reset_n & clock_ready;
    localparam integer STARTUP_BITS=(STARTUP_CYCLES<2) ? 1 : $clog2(STARTUP_CYCLES+1);
    reg [STARTUP_BITS-1:0] startup;
    reg bad_toggle;
    (* async_reg="true" *) reg [1:0] bad_sync;
    reg bad_seen;
    reg [7:0] good_count;
    // ERR is UP XOR DN after a pulse-width filter. There is at most one
    // phase-error event per reference cycle in the supported one-period range.
    always @(posedge phase_bad or negedge control_reset_n)
        if (!control_reset_n) bad_toggle<=1'b0;
        else bad_toggle<=~bad_toggle;
    // Release on the original clock rising edge (the inverted detector
    // reference falling edge), so feedback arrives before its next reference.
    always @(posedge clk or negedge control_reset_n)
        if (!control_reset_n) begin
            startup<=0; pd_enable<=0; locked<=0;
            bad_sync<=0; bad_seen<=0; good_count<=0;
        end else begin
            // Allow the physical control capacitor to reach its resistor
            // preset before closing the loop. Premature release can swallow
            // feedback pulses while the starved delay line is too slow.
            if (!pd_enable) begin
                if (startup==STARTUP_CYCLES-1) pd_enable<=1'b1;
                else startup<=startup+1'b1;
            end
            bad_sync<={bad_sync[0],bad_toggle};
            bad_seen<=bad_sync[1];
            if (!pd_enable || phase_bad || bad_sync[1]!=bad_seen) begin
                locked<=0; good_count<=0;
            end else if (good_count<GOOD_CYCLES) begin
                good_count<=good_count+1'b1;
                locked<=(good_count==GOOD_CYCLES-1);
            end
        end
endmodule
`default_nettype wire
