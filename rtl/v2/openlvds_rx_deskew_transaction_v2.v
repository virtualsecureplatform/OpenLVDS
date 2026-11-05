// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// One RX code update: hold DCC/capture, commit atomically in source_clk,
// require fresh matching physical settling, then await actual DCC warmup.
// hold_clocks controls the real startup/reset path; it never creates a clock.
// settled/update_allowed are backend signals in the source_clk domain.
// clocks_ready/failed come from openlvds_clock_startup_v2 in management domain.
module openlvds_rx_deskew_transaction_v2 #(
    parameter CODE_WIDTH=13,MODEL_ADMITTED=0,TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25,source_clk,reset_n,enable,source_clock_present,
    input wire apply_valid,input wire [CODE_WIDTH-1:0] apply_code,
    output wire apply_ready,output reg apply_done,
    input wire update_allowed,physical_settled,
    input wire [15:0] physical_settled_sequence,
    output reg [CODE_WIDTH-1:0] deskew_code,
    output reg [15:0] deskew_sequence,output reg deskew_commit,
    output wire hold_clocks,busy,
    input wire clocks_ready,clocks_failed,input wire [3:0] clocks_failure_code,
    output reg cal_fail,output reg [3:0] failure_code
);
    localparam IDLE=0,HOLD=1,SEND=2,WAIT_SETTLE=3,WARMUP=4;
    localparam PARAMETERS_VALID=CODE_WIDTH>=1 && CODE_WIDTH<=16 && TIMEOUT_CYCLES>0;
    wire admitted=MODEL_ADMITTED && PARAMETERS_VALID;
    reg [2:0] state;
    reg [15:0] generation,requested_sequence;
    reg [CODE_WIDTH-1:0] requested_code;
    reg [31:0] age;
    reg commit_inflight,commit_seen,settle_seen;
    wire transaction_reset_n=reset_n && enable && admitted && !cal_fail;
    assign hold_clocks=!transaction_reset_n || state==HOLD || state==SEND || state==WAIT_SETTLE;
    assign busy=enable && !cal_fail && state!=IDLE;
    wire code_ready;
    wire [CODE_WIDTH+15:0] committed;
    wire code_received;
    assign apply_ready=transaction_reset_n && source_clock_present && state==IDLE && code_ready;
    (* ASYNC_REG="TRUE" *) reg hold_meta,hold_sync;
    always @(posedge source_clk or negedge transaction_reset_n)
        if(!transaction_reset_n)begin hold_meta<=0;hold_sync<=0;end
        else begin hold_meta<=hold_clocks;hold_sync<=hold_meta;end
    openlvds_code_mailbox_v2 #(.WIDTH(CODE_WIDTH+16)) code_mailbox(
        .reset_n(transaction_reset_n),.source_clk(mgmt_clk_25),.source_valid(state==SEND),
        .source_data({requested_sequence,requested_code}),.source_ready(code_ready),
        .target_clk(source_clk),.target_safe(update_allowed && hold_sync),
        .target_data(committed),.target_valid(code_received));
    // Cancellation flushes transport, but must not asynchronously change the
    // last physical code. Publish only a safe source-clock-domain commit.
    always @(posedge source_clk or negedge reset_n)
        if(!reset_n)begin deskew_code<=0;deskew_sequence<=0;deskew_commit<=0;end
        else begin
            deskew_commit<=0;
            if(transaction_reset_n && code_received && update_allowed && hold_sync)begin
                deskew_code<=committed[CODE_WIDTH-1:0];
                deskew_sequence<=committed[CODE_WIDTH+15:CODE_WIDTH];deskew_commit<=1;
            end
        end

    // Require an unsettled level at or after this physical commit. A low seen
    // only before publication cannot refresh a stale matching high grant.
    reg awaiting_settle,settled_low_seen;
    reg [15:0] active_sequence;
    wire settle_reply_ready;
    wire settle_reply_valid=awaiting_settle && settled_low_seen && hold_sync &&
        physical_settled && physical_settled_sequence==active_sequence;
    always @(posedge source_clk or negedge transaction_reset_n)
        if(!transaction_reset_n)begin awaiting_settle<=0;settled_low_seen<=0;active_sequence<=0;end
        else begin
            if(!hold_sync)settled_low_seen<=0;
            else if(awaiting_settle && !physical_settled)settled_low_seen<=1;
            if(deskew_commit)begin
                awaiting_settle<=1;active_sequence<=deskew_sequence;
                settled_low_seen<=!physical_settled;
            end
            if(settle_reply_valid && settle_reply_ready)awaiting_settle<=0;
        end
    wire settle_reply_pulse;
    wire [15:0] settled_sequence;
    openlvds_code_mailbox_v2 #(.WIDTH(16)) settled_mailbox(
        .reset_n(transaction_reset_n),.source_clk(source_clk),.source_valid(settle_reply_valid),
        .source_data(active_sequence),.source_ready(settle_reply_ready),
        .target_clk(mgmt_clk_25),.target_safe(1'b1),.target_data(settled_sequence),.target_valid(settle_reply_pulse));
    task fail;
        input [3:0] reason;
        begin state<=IDLE;cal_fail<=1;failure_code<=reason;apply_done<=0;end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin
            state<=IDLE;generation<=0;requested_sequence<=0;requested_code<=0;age<=0;
            commit_inflight<=0;commit_seen<=0;settle_seen<=0;apply_done<=0;cal_fail<=0;failure_code<=0;
        end else begin
            apply_done<=0;
            if(!enable)begin
                state<=IDLE;age<=0;commit_inflight<=0;commit_seen<=0;settle_seen<=0;cal_fail<=0;failure_code<=0;
            end else if(!cal_fail)begin
                if(!admitted)fail(4'd8);
                else if(state!=IDLE && !source_clock_present)fail(4'd1);
                else if(state==WARMUP && clocks_failed)fail(clocks_failure_code!=0 ? clocks_failure_code : 4'd1);
                else if(state!=IDLE && !(state==WARMUP && clocks_ready) && age>=TIMEOUT_CYCLES-1)fail(4'd2);
                else begin
                    if(state!=IDLE)age<=age+1'b1;
                    if(!code_ready)commit_inflight<=1;
                    if(code_ready && commit_inflight)commit_seen<=1;
                    if(settle_reply_pulse && settled_sequence==requested_sequence)settle_seen<=1;
                    case(state)
                        IDLE: if(apply_valid && apply_ready)begin
                            generation<=generation+16'd1;requested_sequence<=generation+16'd1;requested_code<=apply_code;
                            age<=0;commit_inflight<=0;commit_seen<=0;settle_seen<=0;state<=HOLD;
                        end
                        // Wait for the old readiness grant to drop before the
                        // new code can even enter the cross-domain mailbox.
                        HOLD: if(!clocks_ready)state<=SEND;
                        SEND: if(code_ready)state<=WAIT_SETTLE;
                        WAIT_SETTLE: if(commit_seen && settle_seen)state<=WARMUP;
                        WARMUP: if(clocks_ready)begin apply_done<=1;state<=IDLE;end
                        default:fail(4'd8);
                    endcase
                end
            end
        end
endmodule
`default_nettype wire
