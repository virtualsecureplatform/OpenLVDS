// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Capture the pair together. Move D1 to its falling-edge holding register
// before the phase-shifted mux selects it; both mux inputs then remain stable
// across selection. This avoids encoded-state clock-to-Q modulation.
(* keep_hierarchy = "yes" *)
module openlvds_ddr_tx_buffer8 (
    input wire clk, input wire select_clk, input wire reset_n,
    input wire [1:0] data, output wire serial
);
`ifdef OPENLVDS_SKY130_TX
    wire rise_bit, fall_bit, held_bit1, clk_n, select_local, mux_serial;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 falling_clock(.A(clk),.Y(clk_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 select_clock(.A(select_clk),.X(select_local));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 rise_sample(.CLK(clk),.D(data[0]),.RESET_B(reset_n),.Q(rise_bit));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 held_sample(.CLK(clk),.D(data[1]),.RESET_B(reset_n),.Q(held_bit1));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_4 fall_sample(.CLK(clk_n),.D(held_bit1),.RESET_B(reset_n),.Q(fall_bit));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__mux2_4 output_logic(.A0(fall_bit),.A1(rise_bit),.S(select_local),.X(mux_serial));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 output_drive(.A(mux_serial),.X(serial));
`else
    reg rise_bit, fall_bit, held_bit1;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin rise_bit <= 1'b0; held_bit1 <= 1'b0; end
        else begin rise_bit <= data[0]; held_bit1 <= data[1]; end
    always @(negedge clk or negedge reset_n)
        if (!reset_n) fall_bit <= 1'b0;
        else fall_bit <= held_bit1;
    assign serial = select_clk ? rise_bit : fall_bit;
`endif
endmodule
`default_nettype wire

// The physical flow reads this declaration; functional regression supplies
// an explicit behavioral cell model instead.
`ifdef OPENLVDS_SKY130_TX
`ifndef OPENLVDS_FUNCTIONAL_CELLS
(* blackbox *) module sky130_fd_sc_hd__buf_8(input wire A, output wire X); endmodule
`endif
`endif
