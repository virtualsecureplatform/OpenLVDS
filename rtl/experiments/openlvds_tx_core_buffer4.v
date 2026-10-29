// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_tx_core (
    input wire clk_400, input wire clk_90, input wire reset_n,
    input wire enable, input wire clock_ready, input wire dll_locked,
    input wire [1:0] tx_data,
    output wire tx_serial, output wire forwarded_clock, output wire tx_ready
);
    wire data_run, clock_run;
    wire qualified_reset_n = reset_n & enable & clock_ready & dll_locked;
    openlvds_reset data_release(.clk(clk_400), .reset_n(qualified_reset_n), .run(data_run));
    openlvds_reset clock_release(.clk(clk_90), .reset_n(qualified_reset_n), .run(clock_run));
    (* keep_hierarchy = "yes", dont_touch = "true" *)
    openlvds_ddr_tx_buffer4 data_launch(.clk(clk_400), .select_clk(clk_90), .reset_n(data_run),
                               .data(tx_data), .serial(tx_serial));
    // Swapped capture/select phases balance clock loading. The 10 pair makes
    // the same mux invert PH0, centering its rising edge in the D0 interval.
    // Native capture cells are retained even for these constant inputs.
    (* keep_hierarchy = "yes", dont_touch = "true" *)
    openlvds_ddr_tx_buffer4 clock_launch(.clk(clk_90), .select_clk(clk_400), .reset_n(clock_run),
                                .data(2'b10), .serial(forwarded_clock));
    assign tx_ready = data_run & clock_run;
endmodule
`default_nettype wire
