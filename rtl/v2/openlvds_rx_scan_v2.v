// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Management-domain RX deskew scan and conservative physical eye selection.
// The ROM port supplies admitted conservative delay intervals for each legal
// code. MODEL_ADMITTED defaults false: no synthetic/default table can start a
// PHY. The release flow must bind the generated ROM and physical model proof.
// apply_done acknowledges the exact atomic code commit. scan_request starts
// a capture-domain four-frame test only after commit and physical settling.
module openlvds_rx_scan_v2 #(
    parameter CODE_WIDTH=13, CODE_COUNT=8192, MODEL_ADMITTED=0,
    parameter SETTLE_CYCLES=2, FRAME_TIMEOUT_CYCLES=80,
    parameter TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25, reset_n, enable, train_req,
    input wire clock_present, dll_locked, table_ready,
    output reg [CODE_WIDTH-1:0] table_index,
    input wire [15:0] delay_lo_ps, delay_hi_ps,
    output wire apply_valid, output reg [CODE_WIDTH-1:0] apply_code,
    input wire apply_ready, apply_done,
    output wire scan_request, input wire scan_valid, scan_pass,
    output reg rx_ready, cal_busy, cal_fail, output reg [3:0] failure_code,
    output reg [15:0] selected_clearance_ps
);
    localparam IDLE=0, WAIT_LOCK=1, TABLE=2, APPLY=3, COMMIT=4, SETTLE=5,
        MEASURE=6, FIND_RUN=7, EXTEND_RUN=8, SCORE=9,
        FINAL_APPLY=10, FINAL_COMMIT=11, FINAL_SETTLE=12, FINAL_MEASURE=13,
        READY=14, FAILED=15;
    reg [3:0] state;
    reg [CODE_COUNT-1:0] passed;
    reg train_seen;
    reg [31:0] age, wait_cycles;
    reg [15:0] previous_lo,previous_hi, left_hi, right_lo;
    reg [CODE_WIDTH-1:0] run_start,run_end,best_code;
    reg found_eye;
    assign apply_valid=enable && clock_present && dll_locked && (state==APPLY || state==FINAL_APPLY);
    assign scan_request=enable && clock_present && dll_locked && (state==MEASURE || state==FINAL_MEASURE);
    wire interval_ordered=delay_hi_ps>=delay_lo_ps;
    wire [16:0] gap={1'b0,delay_hi_ps}-{1'b0,previous_lo};
    wire interval_monotonic=table_index==0 || (delay_lo_ps>previous_hi && gap<=20);
    wire candidate_inside=delay_lo_ps>=left_hi && right_lo>=delay_hi_ps;
    wire [16:0] left_clear={1'b0,delay_lo_ps}-{1'b0,left_hi};
    wire [16:0] right_clear={1'b0,right_lo}-{1'b0,delay_hi_ps};
    wire [16:0] clearance=left_clear<right_clear ? left_clear:right_clear;
    task fail;
        input [3:0] reason;
        begin state<=FAILED;rx_ready<=0;cal_busy<=0;cal_fail<=1;failure_code<=reason;end
    endtask
    task next_scan_code;
        input good;
        begin
            passed[table_index]<=good;
            if(table_index==CODE_COUNT-1) begin table_index<=0;state<=FIND_RUN;end
            else begin table_index<=table_index+1'b1;state<=TABLE;end
        end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n) begin
            state<=IDLE;passed<=0;train_seen<=0;table_index<=0;apply_code<=0;
            age<=0;wait_cycles<=0;previous_lo<=0;previous_hi<=0;left_hi<=0;right_lo<=0;
            run_start<=0;run_end<=0;best_code<=0;found_eye<=0;
            rx_ready<=0;cal_busy<=0;cal_fail<=0;failure_code<=0;selected_clearance_ps<=0;
        end else begin
            train_seen<=train_req;
            if(!enable) begin
                state<=IDLE;train_seen<=0;rx_ready<=0;cal_busy<=0;cal_fail<=0;failure_code<=0;
            end else if(train_req && !train_seen) begin
                state<=WAIT_LOCK;table_index<=0;age<=0;wait_cycles<=0;found_eye<=0;passed<=0;
                rx_ready<=0;cal_busy<=1;cal_fail<=0;failure_code<=0;selected_clearance_ps<=0;
            end else if((cal_busy || rx_ready) && (!MODEL_ADMITTED || !table_ready)) fail(4'd8);
            else if((rx_ready || (cal_busy && state!=WAIT_LOCK)) && !clock_present) fail(4'd1);
            else if((rx_ready || (cal_busy && state!=WAIT_LOCK)) && !dll_locked) fail(4'd4);
            else if(cal_busy && age>=TIMEOUT_CYCLES-1) fail(4'd2);
            else begin
                if(cal_busy)age<=age+1'b1;
                case(state)
                    WAIT_LOCK: if(clock_present && dll_locked)state<=TABLE;
                    TABLE: begin
                        if(!interval_ordered || !interval_monotonic)fail(4'd8);
                        else begin
                            previous_lo<=delay_lo_ps;previous_hi<=delay_hi_ps;
                            apply_code<=table_index;state<=APPLY;
                        end
                    end
                    APPLY: if(apply_ready)state<=COMMIT;
                    COMMIT: if(apply_done)begin wait_cycles<=0;state<=SETTLE;end
                    SETTLE: if(wait_cycles>=SETTLE_CYCLES-1)begin wait_cycles<=0;state<=MEASURE;end
                        else wait_cycles<=wait_cycles+1'b1;
                    MEASURE: begin
                        if(scan_valid)next_scan_code(scan_pass);
                        else if(wait_cycles>=FRAME_TIMEOUT_CYCLES-1)next_scan_code(1'b0);
                        else wait_cycles<=wait_cycles+1'b1;
                    end
                    FIND_RUN: begin
                        if(!interval_ordered)fail(4'd8);
                        else if(passed[table_index]) begin
                            run_start<=table_index;run_end<=table_index;
                            left_hi<=delay_hi_ps;right_lo<=delay_lo_ps;
                            if(table_index==CODE_COUNT-1)state<=SCORE;
                            else begin table_index<=table_index+1'b1;state<=EXTEND_RUN;end
                        end else if(table_index==CODE_COUNT-1)begin
                            if(!found_eye)fail(4'd6);
                            else begin apply_code<=best_code;state<=FINAL_APPLY;end
                        end else table_index<=table_index+1'b1;
                    end
                    EXTEND_RUN: begin
                        if(!interval_ordered)fail(4'd8);
                        else if(passed[table_index])begin
                            run_end<=table_index;right_lo<=delay_lo_ps;
                            if(table_index==CODE_COUNT-1)begin table_index<=run_start;state<=SCORE;end
                            else table_index<=table_index+1'b1;
                        end else begin table_index<=run_start;state<=SCORE;end
                    end
                    SCORE: begin
                        if(!interval_ordered)fail(4'd8);
                        else begin
                            if(candidate_inside && clearance>=250 && (!found_eye || clearance>selected_clearance_ps))begin
                                found_eye<=1;best_code<=table_index;selected_clearance_ps<=clearance[15:0];
                            end
                            if(table_index==run_end)begin
                                // Selection updates above are nonblocking, so the
                                // last candidate needs explicit forwarding here.
                                if(run_end==CODE_COUNT-1)begin
                                    if(candidate_inside && clearance>=250 && (!found_eye || clearance>selected_clearance_ps))begin
                                        apply_code<=table_index;state<=FINAL_APPLY;
                                    end else if(found_eye)begin apply_code<=best_code;state<=FINAL_APPLY;end
                                    else fail(4'd6);
                                end else begin table_index<=run_end+1'b1;state<=FIND_RUN;end
                            end else table_index<=table_index+1'b1;
                        end
                    end
                    FINAL_APPLY: if(apply_ready)state<=FINAL_COMMIT;
                    FINAL_COMMIT: if(apply_done)begin wait_cycles<=0;state<=FINAL_SETTLE;end
                    FINAL_SETTLE: if(wait_cycles>=SETTLE_CYCLES-1)begin wait_cycles<=0;state<=FINAL_MEASURE;end
                        else wait_cycles<=wait_cycles+1'b1;
                    FINAL_MEASURE: begin
                        if(scan_valid)begin
                            if(!scan_pass)fail(4'd7);
                            else begin state<=READY;rx_ready<=1;cal_busy<=0;end
                        end else if(wait_cycles>=FRAME_TIMEOUT_CYCLES-1)fail(4'd7);
                        else wait_cycles<=wait_cycles+1'b1;
                    end
                    default:begin end
                endcase
            end
        end
endmodule
`default_nettype wire
