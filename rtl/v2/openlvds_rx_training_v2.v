// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// RX training integration. Analog I/O, DLL/DCC and generated admitted ROM are
// connected by the future physical wrapper. No ideal clock/delay is generated.
// source_clk is the restored forwarded clock before deskew; sample_clk is the
// actual DLL/DCC capture clock. Both clocks have independent loss monitors.
module openlvds_rx_training_v2 #(
    parameter CODE_WIDTH=13,CODE_COUNT=8192,MODEL_ADMITTED=0,
    parameter TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25,source_clk,sample_clk,reset_n,enable,train_req,dll_locked,
    input wire table_ready,
    output wire [CODE_WIDTH-1:0] table_index,
    input wire [15:0] delay_lo_ps,delay_hi_ps,
    output wire [CODE_WIDTH-1:0] deskew_index,
    output wire deskew_commit,
    input wire [1:0] captured_pair,input wire captured_valid,
    output wire [1:0] rx_data,output wire rx_valid,
    output wire rx_ready,cal_busy,cal_fail,output wire [3:0] failure_code,
    output wire [15:0] selected_clearance_ps
);
    wire raw_present,sample_present;
    openlvds_clock_watch_v2 raw_watch(.reset_n(reset_n),.observed_clk(source_clk),.mgmt_clk_25(mgmt_clk_25),.clock_present(raw_present));
    openlvds_clock_watch_v2 sample_watch(.reset_n(reset_n),.observed_clk(sample_clk),.mgmt_clk_25(mgmt_clk_25),.clock_present(sample_present));
    wire clocks_present=raw_present && sample_present;
    wire apply_valid,apply_ready;
    wire [CODE_WIDTH-1:0] apply_code;
    wire scan_request,scan_valid,scan_pass;
    reg apply_inflight,apply_done;
    // Receiver acknowledges only after the raw-clock domain commits a code.
    // Waiting to observe source_ready low rejects its idle initial high level.
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin apply_inflight<=0;apply_done<=0;end
        else begin
            apply_done<=0;
            if(!apply_ready)apply_inflight<=1;
            if(apply_ready && apply_inflight)begin apply_done<=1;apply_inflight<=0;end
        end
    (* ASYNC_REG="TRUE" *) reg busy_meta,busy_sync;
    always @(posedge source_clk or negedge reset_n)
        if(!reset_n)begin busy_meta<=0;busy_sync<=0;end
        else begin busy_meta<=cal_busy;busy_sync<=busy_meta;end
    openlvds_code_mailbox_v2 #(.WIDTH(CODE_WIDTH)) code_mailbox(
        .reset_n(reset_n),.source_clk(mgmt_clk_25),.source_valid(apply_valid),.source_data(apply_code),
        .source_ready(apply_ready),.target_clk(source_clk),.target_safe(busy_sync),
        .target_data(deskew_index),.target_valid(deskew_commit));

    openlvds_rx_scan_v2 #(.CODE_WIDTH(CODE_WIDTH),.CODE_COUNT(CODE_COUNT),
        .MODEL_ADMITTED(MODEL_ADMITTED),.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) scanner(
        .mgmt_clk_25(mgmt_clk_25),.reset_n(reset_n),.enable(enable),.train_req(train_req),
        .clock_present(clocks_present),.dll_locked(dll_locked),.table_ready(table_ready),
        .table_index(table_index),.delay_lo_ps(delay_lo_ps),.delay_hi_ps(delay_hi_ps),
        .apply_valid(apply_valid),.apply_code(apply_code),.apply_ready(apply_ready),.apply_done(apply_done),
        .scan_request(scan_request),.scan_valid(scan_valid),.scan_pass(scan_pass),
        .rx_ready(rx_ready),.cal_busy(cal_busy),.cal_fail(cal_fail),.failure_code(failure_code),
        .selected_clearance_ps(selected_clearance_ps));

    localparam COMMAND_WIDTH=CODE_WIDTH+8;
    reg [7:0] generation;
    reg command_sent;
    wire command_ready,command_pulse;
    wire [COMMAND_WIDTH-1:0] command;
    wire command_valid=scan_request && !command_sent;
    wire [7:0] next_generation=generation+8'd1;
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin generation<=0;command_sent<=0;end
        else begin
            if(!scan_request)command_sent<=0;
            else if(command_valid && command_ready)begin
                generation<=next_generation;command_sent<=1;
            end
        end
    openlvds_code_mailbox_v2 #(.WIDTH(COMMAND_WIDTH)) command_mailbox(
        .reset_n(reset_n),.source_clk(mgmt_clk_25),.source_valid(command_valid),
        .source_data({next_generation,apply_code}),.source_ready(command_ready),
        .target_clk(sample_clk),.target_safe(1'b1),.target_data(command),.target_valid(command_pulse));

    (* ASYNC_REG="TRUE" *) reg ready_meta,ready_sync,enable_meta,enable_sync;
    always @(posedge sample_clk or negedge reset_n)
        if(!reset_n)begin ready_meta<=0;ready_sync<=0;enable_meta<=0;enable_sync<=0;end
        else begin
            ready_meta<=rx_ready;ready_sync<=ready_meta;
            enable_meta<=enable;enable_sync<=enable_meta;
        end
    wire training_done,training_pass,pair_phase,payload_valid;
    wire [1:0] payload;
    openlvds_training_rx_v2 capture_training(
        .clk_pair(sample_clk),.reset_n(reset_n),.run(enable_sync),.scan_start(command_pulse),
        .pair_valid(captured_valid),.pair_data(captured_pair),.accept_payload(ready_sync),
        .scan_done(training_done),.scan_pass(training_pass),.marker_pair_phase(pair_phase),
        .payload_data(payload),.payload_valid(payload_valid));

    reg active;
    reg [COMMAND_WIDTH-1:0] active_command;
    wire result_ready;
    wire result_valid=active && training_done && !command_pulse;
    always @(posedge sample_clk or negedge reset_n)
        if(!reset_n)begin active<=0;active_command<=0;end
        else if(command_pulse)begin active<=1;active_command<=command;end
        else if(result_valid && result_ready)active<=0;
    wire reply_pulse;
    wire [COMMAND_WIDTH+1:0] reply;
    openlvds_code_mailbox_v2 #(.WIDTH(COMMAND_WIDTH+2)) result_mailbox(
        .reset_n(reset_n),.source_clk(sample_clk),.source_valid(result_valid),
        .source_data({active_command,pair_phase,training_pass}),.source_ready(result_ready),
        .target_clk(mgmt_clk_25),.target_safe(1'b1),.target_data(reply),.target_valid(reply_pulse));
    assign scan_valid=reply_pulse && scan_request && command_sent &&
        reply[COMMAND_WIDTH+1:2]=={generation,apply_code};
    assign scan_pass=reply[0];
    assign rx_data=payload;
    // Management status also masks a stopped sample clock, whose synchronizers
    // cannot advance to clear ready_sync. Assertion of invalid is immediate.
    assign rx_valid=payload_valid && ready_sync && rx_ready && enable && clocks_present && !cal_fail;
endmodule
`default_nettype wire
