// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_ddr_rx (
    input wire clk, input wire reset_n, input wire serial,
    output wire [1:0] data, output wire valid
);
    wire run;
    openlvds_reset reset_release(.clk(clk),.reset_n(reset_n),.run(run));
    wire pair_started;
    // Pair membership matches the preceding receiver at each rising edge.
    // Complete and hold the word on the intervening falling edge, so output
    // settling uses the low half-cycle as well as the original public window.
`ifdef OPENLVDS_SKY130_RX
    wire rise_bit, fall_bit, held_bit, held_valid, clk_n;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 pair_start(.CLK(clk),.D(run),.RESET_B(reset_n),.Q(pair_started));
    wire qualified_rise, qualified_fall, qualified_valid;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_4 falling_clock(.A(clk),.Y(clk_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 rising_sample(.CLK(clk),.D(serial),.RESET_B(reset_n),.Q(rise_bit));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 falling_sample(.CLK(clk_n),.D(serial),.RESET_B(reset_n),.Q(fall_bit));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 rise_enable(.A(rise_bit),.B(run),.X(qualified_rise));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 fall_enable(.A(fall_bit),.B(run),.X(qualified_fall));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 valid_enable(.A(pair_started),.B(run),.X(qualified_valid));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 held_rise(.CLK(clk_n),.D(qualified_rise),.RESET_B(reset_n),.Q(held_bit));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 valid_sample(.CLK(clk_n),.D(qualified_valid),.RESET_B(reset_n),.Q(held_valid));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 data0_drive(.A(held_bit),.X(data[0]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 data1_drive(.A(qualified_fall),.X(data[1]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 valid_drive(.A(held_valid),.X(valid));
`else
    reg rise_bit,fall_bit,held_bit,held_valid,started;
    assign pair_started = started;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) started <= 1'b0;
        else started <= run;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) rise_bit <= 1'b0;
        else rise_bit <= serial;
    always @(negedge clk or negedge reset_n)
        if (!reset_n) begin
            fall_bit <= 1'b0;
            held_bit <= 1'b0;
            held_valid <= 1'b0;
        end else begin
            fall_bit <= serial;
            held_bit <= rise_bit & run;
            held_valid <= pair_started & run;
        end
    assign data = {fall_bit & run,held_bit};
    assign valid = held_valid;
`endif
endmodule
`default_nettype wire
