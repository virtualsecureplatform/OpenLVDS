// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// One retained-event phase trial. Routing remains fixed from clear through
// result consumption. The physical wrapper connects observed_a/b to the two
// conditioned, PRE-SWAP detector inputs and qa/qb to the retained arbiter.
// For period mode the reference pulse is the launcher's next raw epoch.
// Each observed path must contain exactly one event; missing/extra events and
// unresolved arbiter levels cannot grant a valid measurement. SETTLE_CYCLES
// must cover the qualified worst path and detector settling/CDC time.
// Default admission is closed. This controller grants no physical timing proof.
module openlvds_phase_trial_v2 #(
    parameter MODEL_ADMITTED=0,
    parameter SETTLE_CYCLES=4,
    parameter TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,raw_reference,reset_n,enable,clock_present,frontend_ready,
    input wire request_valid,request_next_period,request_swap,
    input wire [1:0] request_section_a,request_section_b,
    input wire [15:0] request_sequence,
    output wire request_ready,busy,
    output reg route_next_period,route_swap,
    output reg [1:0] route_section_a,route_section_b,
    output reg arm,
    output wire launch_pulse,reference_pulse,
    input wire observed_a,observed_b,qa,qb,
    output reg result_valid,
    input wire result_ready,
    output reg [15:0] result_sequence,
    output reg result_epoch_valid,result_detector_valid,
    output reg result_reference_first,result_feedback_first,
    output reg [3:0] failure_code
);
    localparam IDLE=0,CLEAR=1,ARM_WAIT=2,LAUNCH=3,WAIT_LAUNCH=4,SETTLE=5,REPORT=6;
    reg [2:0] state;
    reg [31:0] age,wait_cycles;
    wire allowed=reset_n && enable && clock_present;
    wire trial_active=allowed && state!=IDLE && state!=REPORT;
    wire launch_ready,launch_done,launch_busy;
    assign request_ready=allowed && state==IDLE;
    assign busy=state!=IDLE;
    openlvds_tag_launch_v2 launcher (
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),
        .reset_n(trial_active),.enable(enable),.clock_present(clock_present),
        .request_valid(state==LAUNCH),.request_next_period(route_next_period),
        .request_ready(launch_ready),.busy(launch_busy),.done(launch_done),
        .launch_pulse(launch_pulse),.reference_pulse(reference_pulse)
    );
    wire event_reset_n=allowed && arm;
    reg seen_a,seen_b,duplicate_a,duplicate_b;
    always @(posedge observed_a or negedge event_reset_n)
        if(!event_reset_n)begin seen_a<=0;duplicate_a<=0;end
        else begin seen_a<=1;if(seen_a)duplicate_a<=1;end
    always @(posedge observed_b or negedge event_reset_n)
        if(!event_reset_n)begin seen_b<=0;duplicate_b<=0;end
        else begin seen_b<=1;if(seen_b)duplicate_b<=1;end
    (* ASYNC_REG="TRUE" *) reg [1:0] seen_meta,seen_sync,duplicate_meta,duplicate_sync;
    (* ASYNC_REG="TRUE" *) reg [1:0] level_meta,level_sync,decision_meta,decision_sync;
    always @(posedge mgmt_clk_25 or negedge allowed)
        if(!allowed)begin
            seen_meta<=0;seen_sync<=0;duplicate_meta<=0;duplicate_sync<=0;
            level_meta<=0;level_sync<=0;decision_meta<=0;decision_sync<=0;
        end else begin
            seen_meta<={seen_a,seen_b};seen_sync<=seen_meta;
            duplicate_meta<={duplicate_a,duplicate_b};duplicate_sync<=duplicate_meta;
            level_meta<={observed_a,observed_b};level_sync<=level_meta;
            decision_meta<={qa,qb};decision_sync<=decision_meta;
        end
    task reject;
        input [3:0] reason;
        begin
            arm<=0;result_valid<=1;result_epoch_valid<=0;result_detector_valid<=0;
            result_reference_first<=0;result_feedback_first<=0;failure_code<=reason;state<=REPORT;
        end
    endtask
    always @(posedge mgmt_clk_25 or negedge allowed)
        if(!allowed)begin
            state<=IDLE;age<=0;wait_cycles<=0;arm<=0;
            route_next_period<=0;route_swap<=0;route_section_a<=0;route_section_b<=0;
            result_valid<=0;result_sequence<=0;result_epoch_valid<=0;result_detector_valid<=0;
            result_reference_first<=0;result_feedback_first<=0;failure_code<=0;
        end else begin
            if(state!=IDLE && state!=REPORT)age<=age+1;
            if(state!=IDLE && !frontend_ready && failure_code!=8)reject(4'd8);
            else if(state!=IDLE && state!=REPORT && age>=TIMEOUT_CYCLES-1)reject(4'd2);
            else case(state)
                IDLE:if(request_valid)begin
                    result_sequence<=request_sequence;route_next_period<=request_next_period;
                    route_swap<=request_swap;route_section_a<=request_section_a;route_section_b<=request_section_b;
                    result_valid<=0;result_epoch_valid<=0;result_detector_valid<=0;
                    result_reference_first<=0;result_feedback_first<=0;failure_code<=0;
                    age<=0;wait_cycles<=0;arm<=0;
                    if(!MODEL_ADMITTED || SETTLE_CYCLES<3 || !frontend_ready)reject(4'd8);
                    else state<=CLEAR;
                end
                CLEAR:begin
                    // Three complete management cycles drain old event flags.
                    if(wait_cycles==3)begin
                        if({level_sync,seen_sync,duplicate_sync}==6'b0)begin
                            arm<=1;wait_cycles<=0;state<=ARM_WAIT;
                        end else reject(4'd4);
                    end else wait_cycles<=wait_cycles+1;
                end
                ARM_WAIT:if(wait_cycles==2)begin
                    if({level_sync,seen_sync,duplicate_sync}==6'b0)state<=LAUNCH;
                    else reject(4'd4);
                end else wait_cycles<=wait_cycles+1;
                LAUNCH:if(launch_ready)state<=WAIT_LAUNCH;
                WAIT_LAUNCH:if(launch_done)begin wait_cycles<=0;state<=SETTLE;end
                SETTLE:if(wait_cycles==SETTLE_CYCLES-1)begin
                    case({seen_sync,duplicate_sync,level_sync})
                        6'b110000:begin
                            result_epoch_valid<=1;
                            case(decision_sync)
                                2'b01,2'b10:begin
                                    result_detector_valid<=1;
                                    result_reference_first<=decision_sync==(route_swap ? 2'b10 : 2'b01);
                                    result_feedback_first<=decision_sync==(route_swap ? 2'b01 : 2'b10);
                                    result_valid<=1;state<=REPORT;
                                end
                                default:reject(4'd5);
                            endcase
                        end
                        default:reject(4'd4);
                    endcase
                end else wait_cycles<=wait_cycles+1;
                REPORT:if(result_ready)begin arm<=0;result_valid<=0;state<=IDLE;end
                default:reject(4'd4);
            endcase
        end
endmodule
`default_nettype wire
