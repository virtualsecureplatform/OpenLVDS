// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_ddr_rx (
    input wire clk, input wire reset_n, input wire serial,
    output reg [1:0] data, output reg valid
);
    wire run;
    openlvds_reset reset_release(.clk(clk), .reset_n(reset_n), .run(run));
    reg rise_bit, pair_started;
`ifdef OPENLVDS_SKY130_RX
    wire fall_bit,clk_n;
    // The positive-edge resettable cell has a shorter input aperture than
    // dfrtn_1. An explicit retained inverter supplies its falling-edge clock.
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
    // Sample continuously; suppress invalid startup pairs at the parallel port.
    // A run-enable mux on the sampling input needlessly consumes eye margin.
    always @(posedge clk or negedge reset_n)
        if (!reset_n) rise_bit <= 1'b0;
        else rise_bit <= serial;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin
            pair_started <= 1'b0;
            data <= 2'b00; valid <= 1'b0;
        end else if (!run) begin
            pair_started <= 1'b0;
            data <= 2'b00; valid <= 1'b0;
        end else begin
            pair_started <= 1'b1;
            data <= {fall_bit, rise_bit};
            valid <= pair_started;
        end
endmodule
`default_nettype wire
