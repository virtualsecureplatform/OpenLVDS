// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// One management timeout spans DLL calibration and delivered-clock warmup.
// Stage flags come from the actual controllers; they are not timing models.
module openlvds_clock_sequence_v2 #(parameter TIMEOUT_CYCLES=2500000)(
    input wire mgmt_clk_25,reset_n,enable,train_req,
    input wire dll_locked,dll_fail,startup_ready,startup_fail,
    input wire [3:0] dll_failure_code,startup_failure_code,
    output wire bank_enable,start_dll,startup_enable,outputs_valid,cal_busy,cal_fail,
    output reg [3:0] failure_code
);
    localparam IDLE=0,START=1,CALIBRATE=2,WARMUP=3,READY=4,FAILED=5;
    reg [2:0] state;
    reg train_seen;
    reg [31:0] age;
    wire restart=train_req && !train_seen;
    assign bank_enable=enable && !restart && state!=IDLE && state!=FAILED;
    assign start_dll=bank_enable && state==START;
    assign startup_enable=bank_enable && (state==WARMUP || state==READY);
    assign outputs_valid=startup_enable && state==READY && dll_locked && startup_ready && !dll_fail && !startup_fail;
    assign cal_busy=bank_enable && state!=READY;
    assign cal_fail=enable && state==FAILED;
    task fail;
        input [3:0] reason;
        begin state<=FAILED;failure_code<=reason;end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin state<=IDLE;train_seen<=0;age<=0;failure_code<=0;end
        else begin
            train_seen<=train_req;
            if(!enable)begin state<=IDLE;train_seen<=0;age<=0;failure_code<=0;end
            else if(restart)begin
                age<=0;failure_code<=0;
                if(TIMEOUT_CYCLES<=0)fail(4'd8);else state<=START;
            end else if(state!=IDLE && state!=FAILED)begin
                if(dll_fail)fail(dll_failure_code);
                else if(startup_enable && startup_fail)fail(startup_failure_code);
                else if((state==WARMUP || state==READY) && !dll_locked)fail(4'd1);
                else if(state==READY && !startup_ready)fail(4'd1);
                // A fully ready stage observed at the deadline may complete;
                // merely reaching DLL lock cannot renew the overall budget.
                else if(state!=READY && !(state==WARMUP && startup_ready) && age>=TIMEOUT_CYCLES-1)fail(4'd2);
                else begin
                    if(state!=READY)age<=age+1;
                    case(state)
                        START:state<=CALIBRATE;
                        CALIBRATE:if(dll_locked)state<=WARMUP;
                        WARMUP:if(startup_ready)state<=READY;
                        default:begin end
                    endcase
                end
            end
        end
endmodule
`default_nettype wire
