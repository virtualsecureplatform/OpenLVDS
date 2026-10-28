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
`ifdef OPENLVDS_SKY130_TX
    wire rise_state, fall_state, held_bit1;
    wire rise_next, fall_next, clk_n;
    // Keep the data and constant-input clock replica on the same native cells.
    // Only one output-XOR operand changes per edge; avoid decomposed NAND paths.
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__xor2_1 rise_logic(.A(data[0]),.B(fall_state),.X(rise_next));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__xor2_1 fall_logic(.A(held_bit1),.B(rise_state),.X(fall_next));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 falling_clock(.A(clk),.Y(clk_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 rise_sample(.CLK(clk),.D(rise_next),.RESET_B(reset_n),.Q(rise_state));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 held_sample(.CLK(clk),.D(data[1]),.RESET_B(reset_n),.Q(held_bit1));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 fall_sample(.CLK(clk_n),.D(fall_next),.RESET_B(reset_n),.Q(fall_state));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__xor2_4 output_logic(.A(rise_state),.B(fall_state),.X(serial));
`else
    (* keep = "true" *) reg rise_state, fall_state, held_bit1;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin rise_state <= 1'b0; held_bit1 <= 1'b0; end
        else begin rise_state <= data[0] ^ fall_state; held_bit1 <= data[1]; end
    always @(negedge clk or negedge reset_n)
        if (!reset_n) fall_state <= 1'b0;
        else fall_state <= held_bit1 ^ rise_state;
    assign serial = rise_state ^ fall_state;
`endif
endmodule
`default_nettype wire
