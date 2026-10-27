// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Only one XOR operand changes per edge. D1 belongs to the same input pair
// as D0, and therefore must be captured on the rising edge, not the falling.
// Opposite-edge feedback paths are REAL half-cycle paths; never false-path them.
(* keep_hierarchy = "yes" *)
module openlvds_ddr_tx (
    input wire clk, input wire reset_n, input wire [1:0] data,
    output wire serial
);
    (* keep = "true" *) reg rise_state, fall_state, held_bit1;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin rise_state <= 1'b0; held_bit1 <= 1'b0; end
        else begin rise_state <= data[0] ^ fall_state; held_bit1 <= data[1]; end
    always @(negedge clk or negedge reset_n)
        if (!reset_n) fall_state <= 1'b0;
        else fall_state <= held_bit1 ^ rise_state;
    assign serial = rise_state ^ fall_state;
endmodule
`default_nettype wire
