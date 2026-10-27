// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_rx (
    input wire rx_p, input wire rx_n, input wire rx_clk_p, input wire rx_clk_n,
    input wire reset_n, input wire enable,
    output wire [1:0] rx_data, output wire rx_clk_400, output wire rx_valid,
    input wire VREF, inout wire IREF,
    inout wire VDDIO, inout wire VDDD, inout wire VSS
);
    wire nb,serial;
    lvds_bias bias(IREF,nb,VDDIO,VSS);
    openlvds_receiver_core data_receiver(rx_p,rx_n,serial,VREF,IREF,nb,VDDIO,VDDD,VSS);
    openlvds_receiver_core clock_receiver(rx_clk_p,rx_clk_n,rx_clk_400,VREF,IREF,nb,VDDIO,VDDD,VSS);
    // rx_valid qualifies pair assembly, not remote payload/training semantics.
    openlvds_ddr_rx digital(rx_clk_400,reset_n & enable,serial,rx_data,rx_valid);
endmodule
`default_nettype wire
