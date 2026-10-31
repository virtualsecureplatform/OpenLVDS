// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_ddr_rx (
    input wire clk, input wire reset_n, input wire serial,
    output wire [1:0] data, output wire valid
);
    wire run;
    openlvds_reset reset_release(.clk(clk), .reset_n(reset_n), .run(run));
    reg rise_bit, pair_started, published_valid;
`ifdef OPENLVDS_SKY130_RX
    wire fall_bit, clk_n;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__inv_1 falling_clock(.A(clk),.Y(clk_n));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 falling_sample(.CLK(clk_n),.D(serial),
        .RESET_B(reset_n),.Q(fall_bit));
`else
    reg fall_bit;
    always @(negedge clk or negedge reset_n)
        if (!reset_n) fall_bit <= 1'b0;
        else fall_bit <= serial;
`endif
    always @(posedge clk or negedge reset_n)
        if (!reset_n) rise_bit <= 1'b0;
        else rise_bit <= serial;
`ifdef OPENLVDS_SKY130_RX
    wire [1:0] published_data;
    wire [1:0] publish_input = run ? {fall_bit, rise_bit} : 2'b00;
    // Controlled comparison: retain the same buf_8 outputs and pipeline,
    // using unit-strength publication flops to isolate their internal delay.
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 data0_publish(.CLK(clk),.D(publish_input[0]),
        .RESET_B(reset_n),.Q(published_data[0]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfrtp_1 data1_publish(.CLK(clk),.D(publish_input[1]),
        .RESET_B(reset_n),.Q(published_data[1]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 data0_drive(.A(published_data[0]),.X(data[0]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_8 data1_drive(.A(published_data[1]),.X(data[1]));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_1 valid_drive(.A(published_valid),.X(valid));
`else
    reg [1:0] published_data;
    assign data = published_data;
    assign valid = published_valid;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) published_data <= 2'b00;
        else if (!run) published_data <= 2'b00;
        else published_data <= {fall_bit, rise_bit};
`endif
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin
            pair_started <= 1'b0;
            published_valid <= 1'b0;
        end else if (!run) begin
            pair_started <= 1'b0;
            published_valid <= 1'b0;
        end else begin
            pair_started <= 1'b1;
            published_valid <= pair_started;
        end
endmodule
`default_nettype wire
