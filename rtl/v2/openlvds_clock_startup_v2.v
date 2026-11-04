// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// DCC release and warmup use the actual physical raw/delivered clocks. No
// clock is synthesized here. DCC admission is separate from DLL admission.
// ready0/ready90 assert synchronously in their own delivered clock domain and
// clear asynchronously even if that clock has stopped.
module openlvds_clock_startup_v2 #(
    parameter DCC_MODEL_ADMITTED=0,WARMUP_CYCLES=256,TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25,raw_phase0,raw_phase90,clock0,clock90,
    input wire reset_n,enable,dll_locked,source_clock_present,
    output wire dcc_reset0_n,dcc_reset90_n,
    output wire clocks_ready,ready0,ready90,cal_busy,
    output reg cal_fail,
    output reg [3:0] failure_code
);
    localparam PARAMETERS_VALID=WARMUP_CYCLES>=256 && WARMUP_CYCLES<=65535 && TIMEOUT_CYCLES>0;
    wire admitted=DCC_MODEL_ADMITTED && PARAMETERS_VALID;
    wire allowed=reset_n && enable && dll_locked && source_clock_present && admitted && !cal_fail;
    openlvds_dcc_release_v2 release_control(
        .raw_phase0(raw_phase0),.raw_phase90(raw_phase90),.reset_n(reset_n),.enable(enable && admitted && !cal_fail),
        .clock_present(source_clock_present),.dll_locked(dll_locked),.reset0_n(dcc_reset0_n),.reset90_n(dcc_reset90_n));
    wire warm_reset0_n=allowed && dcc_reset0_n;
    wire warm_reset90_n=allowed && dcc_reset90_n;
    reg [15:0] cycles0,cycles90;
    reg warm0,warm90;
    always @(posedge clock0 or negedge warm_reset0_n)
        if(!warm_reset0_n)begin cycles0<=0;warm0<=0;end
        else if(!warm0)begin
            cycles0<=cycles0+16'd1;
            if(cycles0==WARMUP_CYCLES-1)warm0<=1;
        end
    always @(posedge clock90 or negedge warm_reset90_n)
        if(!warm_reset90_n)begin cycles90<=0;warm90<=0;end
        else if(!warm90)begin
            cycles90<=cycles90+16'd1;
            if(cycles90==WARMUP_CYCLES-1)warm90<=1;
        end
    (* ASYNC_REG="TRUE" *) reg warm0_meta,warm0_sync,warm90_meta,warm90_sync;
    always @(posedge mgmt_clk_25 or negedge allowed)
        if(!allowed)begin warm0_meta<=0;warm0_sync<=0;warm90_meta<=0;warm90_sync<=0;end
        else begin warm0_meta<=warm0;warm0_sync<=warm0_meta;warm90_meta<=warm90;warm90_sync<=warm90_meta;end
    wire present0,present90;
    // A DCC's reset output can itself create an edge. Discard all pre-release
    // heartbeat history, so a restart cannot mistake that old edge for a
    // newly running clock and then report a false loss during CDC refill.
    openlvds_clock_watch_v2 clock0_watch(.reset_n(warm_reset0_n),.observed_clk(clock0),.mgmt_clk_25(mgmt_clk_25),.clock_present(present0));
    openlvds_clock_watch_v2 clock90_watch(.reset_n(warm_reset90_n),.observed_clk(clock90),.mgmt_clk_25(mgmt_clk_25),.clock_present(present90));
    assign clocks_ready=allowed && warm0_sync && warm90_sync && present0 && present90;
    wire ready_reset_n=reset_n && clocks_ready;
    (* ASYNC_REG="TRUE" *) reg ready0_meta,ready0_sync,ready90_meta,ready90_sync;
    always @(posedge clock0 or negedge ready_reset_n)
        if(!ready_reset_n)begin ready0_meta<=0;ready0_sync<=0;end
        else begin ready0_meta<=1;ready0_sync<=ready0_meta;end
    always @(posedge clock90 or negedge ready_reset_n)
        if(!ready_reset_n)begin ready90_meta<=0;ready90_sync<=0;end
        else begin ready90_meta<=1;ready90_sync<=ready90_meta;end
    assign ready0=ready0_sync;
    assign ready90=ready90_sync;
    assign cal_busy=enable && dll_locked && !cal_fail && !clocks_ready;
    reg seen0,seen90;
    reg [31:0] age;
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin age<=0;seen0<=0;seen90<=0;cal_fail<=0;failure_code<=0;end
        else if(!enable || !dll_locked)begin age<=0;seen0<=0;seen90<=0;cal_fail<=0;failure_code<=0;end
        else if(!cal_fail)begin
            if(present0)seen0<=1;
            if(present90)seen90<=1;
            if(!admitted)begin cal_fail<=1;failure_code<=8;end
            else if(!source_clock_present || (seen0 && !present0) || (seen90 && !present90))begin
                cal_fail<=1;failure_code<=1;
            end else if(!clocks_ready)begin
                if(age>=TIMEOUT_CYCLES-1)begin cal_fail<=1;failure_code<=2;end
                else age<=age+1;
            end
        end
endmodule
`default_nettype wire
