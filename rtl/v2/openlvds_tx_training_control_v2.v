// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// External physical DLL/DCC clocks are mandatory. The dedicated forwarded
// clock remains a physical DCC output; no constant-data DDR mux creates it.
// payload is preloaded and synchronous to clock0 before the lab controller
// ends training. train_req is a management-domain level held until RX ready.
module openlvds_tx_training_control_v2 #(
    parameter DCC_MODEL_ADMITTED=0,WARMUP_CYCLES=256,TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25,raw_phase0,raw_phase90,clock0,clock90,
    input wire reset_n,enable,dll_locked,source_clock_present,train_req,
    input wire [1:0] payload,
    output wire dcc_reset0_n,dcc_reset90_n,clocks_ready,
    output wire cal_busy,cal_fail,
    output wire [3:0] failure_code,
    output wire [1:0] pair_data,
    output wire pair_valid,payload_active
);
    wire ready0;
    openlvds_clock_startup_v2 #(.DCC_MODEL_ADMITTED(DCC_MODEL_ADMITTED),.WARMUP_CYCLES(WARMUP_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) startup(
        .mgmt_clk_25(mgmt_clk_25),.raw_phase0(raw_phase0),.raw_phase90(raw_phase90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.dll_locked(dll_locked),.source_clock_present(source_clock_present),
        .dcc_reset0_n(dcc_reset0_n),.dcc_reset90_n(dcc_reset90_n),.clocks_ready(clocks_ready),
        .ready0(ready0),.ready90(),.cal_busy(cal_busy),.cal_fail(cal_fail),.failure_code(failure_code));
    (* ASYNC_REG="TRUE" *) reg train_meta,train_sync;
    always @(posedge clock0 or negedge reset_n)
        if(!reset_n)begin train_meta<=1;train_sync<=1;end
        else begin train_meta<=train_req;train_sync<=train_meta;end
    openlvds_training_tx_v2 training(
        .clk_pair(clock0),.reset_n(reset_n),.run(ready0),.train_req(train_sync),.payload(payload),
        .pair_data(pair_data),.payload_active(payload_active));
    assign pair_valid=ready0;
endmodule
`default_nettype wire
