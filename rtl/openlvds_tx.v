// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_tx #(
    parameter integer WARMUP_CYCLES=256
) (
    input wire clk_400, input wire reset_n, input wire enable,
    input wire clock_ready, input wire [1:0] tx_data,
    output wire tx_p, output wire tx_n,
    output wire tx_clk_p, output wire tx_clk_n,
    output wire tx_ready, output wire dll_locked,
    input wire VREF, inout wire IREF,
    inout wire VDDIO, inout wire VDDD, inout wire VSS
);
    wire nb,clk0,clk90,clk180,clk270,feedback,phase_bad,up,dn,pd_enable;
    wire tx_serial,clock_serial,core_ready;
    lvds_bias bias(IREF,nb,VDDIO,VSS);
    openlvds_dll_core dll(clk_400,reset_n,pd_enable,clk0,clk90,clk180,clk270,
        feedback,phase_bad,up,dn,IREF,VDDIO,VDDD,VSS);
    openlvds_dll_control control(clk0,reset_n,clock_ready & enable,
                                phase_bad,pd_enable,dll_locked);
    localparam integer CW=(WARMUP_CYCLES<2)?1:$clog2(WARMUP_CYCLES+1);
    reg [CW-1:0] warmup;
    wire warm_reset_n=reset_n & enable & clock_ready & dll_locked;
    always @(posedge clk0 or negedge warm_reset_n)
        if (!warm_reset_n) warmup<=0;
        else if (!core_ready) warmup<=0;
        else if (warmup<WARMUP_CYCLES) warmup<=warmup+1'b1;
    assign tx_ready=core_ready && warmup==WARMUP_CYCLES;
    // Alternating startup data lets the driver's common-mode loop settle
    // under switching load before advertising payload readiness.
    wire [1:0] launch_data=tx_ready ? tx_data : 2'b01;
    openlvds_tx_core digital(clk0,clk90,reset_n,enable,clock_ready,dll_locked,
                             launch_data,tx_serial,clock_serial,core_ready);
    openlvds_driver_core data_driver(tx_serial,tx_p,tx_n,VREF,IREF,nb,VDDIO,VDDD,VSS);
    openlvds_driver_core clock_driver(clock_serial,tx_clk_p,tx_clk_n,VREF,IREF,nb,VDDIO,VDDD,VSS);
endmodule
`default_nettype wire
