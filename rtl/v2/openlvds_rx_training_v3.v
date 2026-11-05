// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// RX training with real clock startup and per-code physical transactions.
// All raw phases, DCC outputs, captured data and settling grants are backend
// inputs. No clock/delay is generated. Admissions require separate proofs.
module openlvds_rx_training_v3 #(
    parameter CODE_WIDTH=13,CODE_COUNT=8192,CODE_MODEL_ADMITTED=0,
    parameter DESKEW_MODEL_ADMITTED=0,DCC_MODEL_ADMITTED=0,
    parameter WARMUP_CYCLES=256,TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25,source_clk,raw_phase0,raw_phase90,clock0,clock90,
    input wire reset_n,enable,train_req,dll_locked,dll_failed,
    input wire [3:0] dll_failure_code,
    output wire dll_enable,output reg dll_train,
    input wire table_ready,output wire [CODE_WIDTH-1:0] table_index,
    input wire [15:0] delay_lo_ps,delay_hi_ps,
    input wire update_allowed,physical_settled,
    input wire [15:0] physical_settled_sequence,
    output wire [CODE_WIDTH-1:0] deskew_index,
    output wire [15:0] deskew_sequence,output wire deskew_commit,
    output wire dcc_reset0_n,dcc_reset90_n,clocks_ready,source_clock_present,
    input wire [1:0] captured_pair,input wire captured_valid,
    output wire [1:0] rx_data,output wire rx_valid,rx_ready,cal_busy,
    output reg cal_fail,output reg [3:0] failure_code,
    output wire [15:0] selected_clearance_ps
);
    localparam PARAMETERS_VALID=CODE_WIDTH>=1 && CODE_WIDTH<=16 && CODE_COUNT>=2 &&
        CODE_COUNT<=(2**CODE_WIDTH) && TIMEOUT_CYCLES>0 && WARMUP_CYCLES>=256 && WARMUP_CYCLES<=65535;
    wire admitted=CODE_MODEL_ADMITTED && DESKEW_MODEL_ADMITTED && DCC_MODEL_ADMITTED && PARAMETERS_VALID;
    reg active,train_seen,raw_seen,dll_seen;
    reg [31:0] age;
    wire train_edge=train_req && !train_seen;
    wire run=reset_n && enable && active && !train_edge && !cal_fail && admitted && table_ready;
    assign dll_enable=run;
    openlvds_clock_watch_v2 raw_watch(.reset_n(reset_n),.observed_clk(source_clk),
        .mgmt_clk_25(mgmt_clk_25),.clock_present(source_clock_present));
    wire transaction_busy,hold_clocks,transaction_failed;
    wire [3:0] transaction_failure;
    wire startup_failed,startup_clock_loss,scan_ready,scan_busy,scan_failed;
    wire [3:0] startup_failure,scan_failure;
    wire apply_valid,apply_ready,apply_done;
    wire [CODE_WIDTH-1:0] apply_code;
    wire scan_request,scan_valid,scan_pass;
    // During an intentional code update the delivered clocks must stop. The
    // predeskew source must remain present throughout, including this hold.
    wire scan_clocks_present=source_clock_present && (transaction_busy || clocks_ready);
    openlvds_rx_deskew_transaction_v2 #(.CODE_WIDTH(CODE_WIDTH),.MODEL_ADMITTED(DESKEW_MODEL_ADMITTED),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) transaction(
        .mgmt_clk_25(mgmt_clk_25),.source_clk(source_clk),.reset_n(reset_n),.enable(run),
        .source_clock_present(source_clock_present),.apply_valid(apply_valid),.apply_code(apply_code),
        .apply_ready(apply_ready),.apply_done(apply_done),.update_allowed(update_allowed),
        .physical_settled(physical_settled),.physical_settled_sequence(physical_settled_sequence),
        .deskew_code(deskew_index),.deskew_sequence(deskew_sequence),.deskew_commit(deskew_commit),
        .hold_clocks(hold_clocks),.busy(transaction_busy),.clocks_ready(clocks_ready),
        .clocks_failed(startup_failed),.clocks_failure_code(startup_failure),
        .cal_fail(transaction_failed),.failure_code(transaction_failure));
    openlvds_clock_startup_v3 #(.DCC_MODEL_ADMITTED(DCC_MODEL_ADMITTED),.WARMUP_CYCLES(WARMUP_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) startup(
        .mgmt_clk_25(mgmt_clk_25),.raw_phase0(raw_phase0),.raw_phase90(raw_phase90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(run && source_clock_present && !hold_clocks),.dll_locked(dll_locked),
        .source_clock_present(source_clock_present),.dcc_reset0_n(dcc_reset0_n),.dcc_reset90_n(dcc_reset90_n),
        .clocks_ready(clocks_ready),.ready0(),.ready90(),.cal_busy(),.clock_loss(startup_clock_loss),.cal_fail(startup_failed),.failure_code(startup_failure));
    openlvds_rx_scan_v2 #(.CODE_WIDTH(CODE_WIDTH),.CODE_COUNT(CODE_COUNT),.MODEL_ADMITTED(CODE_MODEL_ADMITTED),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) scanner(
        .mgmt_clk_25(mgmt_clk_25),.reset_n(reset_n),.enable(run),.train_req(dll_train),
        .clock_present(scan_clocks_present),.dll_locked(dll_locked),.table_ready(table_ready),
        .table_index(table_index),.delay_lo_ps(delay_lo_ps),.delay_hi_ps(delay_hi_ps),
        .apply_valid(apply_valid),.apply_code(apply_code),.apply_ready(apply_ready),.apply_done(apply_done),
        .scan_request(scan_request),.scan_valid(scan_valid),.scan_pass(scan_pass),
        .rx_ready(scan_ready),.cal_busy(scan_busy),.cal_fail(scan_failed),.failure_code(scan_failure),
        .selected_clearance_ps(selected_clearance_ps));
    task fail;
        input [3:0] reason;
        begin cal_fail<=1;failure_code<=reason;active<=0;end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin active<=0;train_seen<=0;raw_seen<=0;dll_seen<=0;age<=0;dll_train<=0;cal_fail<=0;failure_code<=0;end
        else begin
            train_seen<=train_req;dll_train<=0;
            if(!enable)begin active<=0;train_seen<=0;raw_seen<=0;dll_seen<=0;age<=0;cal_fail<=0;failure_code<=0;end
            else if(train_edge)begin active<=1;dll_train<=1;raw_seen<=0;dll_seen<=0;age<=0;cal_fail<=0;failure_code<=0;end
            else if(active && !cal_fail)begin
                if(source_clock_present)raw_seen<=1;
                if(dll_locked)dll_seen<=1;
                if(!admitted || !table_ready)fail(4'd8);
                else if(raw_seen && !source_clock_present)fail(4'd1);
                else if(dll_seen && !dll_locked)fail(4'd4);
                else if(dll_failed)fail(dll_failure_code!=0 ? dll_failure_code : 4'd4);
                else if(startup_clock_loss)fail(4'd1);
                else if(transaction_failed)fail(transaction_failure);
                else if(startup_failed)fail(startup_failure);
                else if(scan_failed)fail(scan_failure);
                else if(!scan_ready)begin
                    if(age>=TIMEOUT_CYCLES-1)fail(4'd2);
                    else age<=age+1'b1;
                end
            end
        end
    assign rx_ready=run && scan_ready && clocks_ready && source_clock_present && dll_locked &&
        !transaction_failed && !startup_failed && !scan_failed && admitted && table_ready;
    assign cal_busy=run && !rx_ready;

    // Flush command, result and payload state whenever capture stops. This
    // also discards a pending old result when an update cancels its scan.
    wire capture_reset_n=run && clocks_ready && !transaction_busy;
    localparam COMMAND_WIDTH=CODE_WIDTH+16;
    reg [15:0] generation;
    reg command_sent;
    wire command_ready,command_pulse;
    wire [COMMAND_WIDTH-1:0] command;
    wire command_valid=capture_reset_n && scan_request && !command_sent;
    wire [15:0] next_generation=generation+16'd1;
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)generation<=0;
        else if(command_valid && command_ready)generation<=next_generation;
    always @(posedge mgmt_clk_25 or negedge capture_reset_n)
        if(!capture_reset_n)command_sent<=0;
        else if(!scan_request)command_sent<=0;
        else if(command_valid && command_ready)command_sent<=1;
    openlvds_code_mailbox_v2 #(.WIDTH(COMMAND_WIDTH)) command_mailbox(
        .reset_n(capture_reset_n),.source_clk(mgmt_clk_25),.source_valid(command_valid),
        .source_data({next_generation,apply_code}),.source_ready(command_ready),
        .target_clk(clock0),.target_safe(1'b1),.target_data(command),.target_valid(command_pulse));
    (* ASYNC_REG="TRUE" *) reg ready_meta,ready_sync,run_meta,run_sync;
    always @(posedge clock0 or negedge capture_reset_n)
        if(!capture_reset_n)begin ready_meta<=0;ready_sync<=0;run_meta<=0;run_sync<=0;end
        else begin ready_meta<=rx_ready;ready_sync<=ready_meta;run_meta<=1;run_sync<=run_meta;end
    wire training_done,training_pass,pair_phase,payload_valid;
    wire [1:0] payload;
    openlvds_training_rx_v2 capture_training(
        .clk_pair(clock0),.reset_n(capture_reset_n),.run(run_sync),.scan_start(command_pulse),
        .pair_valid(captured_valid),.pair_data(captured_pair),.accept_payload(ready_sync),
        .scan_done(training_done),.scan_pass(training_pass),.marker_pair_phase(pair_phase),
        .payload_data(payload),.payload_valid(payload_valid));
    reg result_pending;
    reg [COMMAND_WIDTH-1:0] active_command;
    wire result_ready;
    wire result_valid=result_pending && training_done && !command_pulse;
    always @(posedge clock0 or negedge capture_reset_n)
        if(!capture_reset_n)begin result_pending<=0;active_command<=0;end
        else if(command_pulse)begin result_pending<=1;active_command<=command;end
        else if(result_valid && result_ready)result_pending<=0;
    wire reply_pulse;
    wire [COMMAND_WIDTH+1:0] reply;
    openlvds_code_mailbox_v2 #(.WIDTH(COMMAND_WIDTH+2)) result_mailbox(
        .reset_n(capture_reset_n),.source_clk(clock0),.source_valid(result_valid),
        .source_data({active_command,pair_phase,training_pass}),.source_ready(result_ready),
        .target_clk(mgmt_clk_25),.target_safe(1'b1),.target_data(reply),.target_valid(reply_pulse));
    assign scan_valid=capture_reset_n && reply_pulse && scan_request && command_sent &&
        reply[COMMAND_WIDTH+1:2]=={generation,apply_code};
    assign scan_pass=reply[0];
    assign rx_data=payload;
    assign rx_valid=payload_valid && ready_sync && rx_ready && capture_reset_n;
endmodule
`default_nettype wire
