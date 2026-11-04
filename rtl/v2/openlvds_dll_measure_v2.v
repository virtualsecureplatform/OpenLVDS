// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// All-pairs section balancing and independent unwrapped period brackets.
// Offset=0 delays the reference branch; offset=1 delays the feedback branch.
// The physical wrapper MUST characterize both offsets, including detector bias,
// to bound each effective threshold within the required +/-20 ps tolerance.
// Each offset is voted independently in both normalized input-swap directions.
// A section is eliminated only if another section is strictly faster outside
// the bracket. Six pairs also test the complete max/min spread, avoiding an
// accumulated chain of pairwise "near enough" decisions.
// No physical/model admission is inferred from this protocol engine.
module openlvds_dll_measure_v2 #(
    parameter MODEL_ADMITTED=0,parameter VOTES=3,parameter MAX_RETRIES=3
)(
    input wire mgmt_clk_25,reset_n,enable,clock_present,
    input wire measure_request,separated_mode,
    output wire measure_valid,
    output reg measure_epoch_valid,measure_detector_valid,measure_balanced,
    output reg [1:0] measure_fastest,
    output reg measure_period_short,measure_period_long,
    output reg [3:0] failure_code,
    output wire trial_cancel,trial_request_valid,
    input wire trial_request_ready,trial_routes_applied,
    input wire [15:0] trial_routes_sequence,
    output wire trial_next_period,trial_swap,trial_positive_offset,
    output wire [1:0] trial_section_a,trial_section_b,
    output wire [15:0] trial_sequence,
    input wire trial_result_valid,
    output wire trial_result_ready,
    input wire [15:0] trial_result_sequence,
    input wire trial_epoch_valid,trial_detector_valid,
    input wire trial_reference_first,trial_feedback_first,
    input wire [3:0] trial_failure_code
);
    localparam IDLE=0,ROUTE=1,ISSUE=2,WAIT_RESULT=3,REPORT=4,WAIT_RELEASE=5;
    reg [2:0] state,pair_index;
    reg period_mode,swap,positive_offset,swap0_vote,negative_vote,balanced;
    reg [15:0] sequence_id,vote_count,ones,retries;
    reg [3:0] slower;
    reg [3:0] next_slower;
    reg pair_tied;
    wire active=state==ROUTE || state==ISSUE || state==WAIT_RESULT;
    wire allowed=enable && clock_present && measure_request;
    assign measure_valid=allowed && state==REPORT;
    assign trial_cancel=!allowed || !active;
    assign trial_request_valid=allowed && state==ISSUE;
    assign trial_result_ready=allowed && state==WAIT_RESULT;
    assign trial_next_period=period_mode;
    assign trial_swap=swap;
    assign trial_positive_offset=positive_offset;
    assign trial_sequence=sequence_id;
    function [1:0] pair_a;
        input [2:0] index;
        case(index)0,1,2:pair_a=0;3,4:pair_a=1;default:pair_a=2;endcase
    endfunction
    function [1:0] pair_b;
        input [2:0] index;
        case(index)0:pair_b=1;1,3:pair_b=2;default:pair_b=3;endcase
    endfunction
    assign trial_section_a=period_mode ? 2'd0 : pair_a(pair_index);
    assign trial_section_b=period_mode ? 2'd0 : pair_b(pair_index);
    wire majority=(ones+(trial_reference_first ? 16'd1 : 16'd0))>VOTES/2;
    task reject;
        input [3:0] reason;
        begin
            measure_epoch_valid<=0;measure_detector_valid<=0;measure_balanced<=0;
            measure_period_short<=0;measure_period_long<=0;failure_code<=reason;state<=REPORT;
        end
    endtask
    task next_trial;
        begin sequence_id<=sequence_id+1'b1;state<=ROUTE;end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin
            state<=IDLE;pair_index<=0;period_mode<=0;swap<=0;positive_offset<=0;
            swap0_vote<=0;negative_vote<=0;balanced<=0;sequence_id<=0;
            vote_count<=0;ones<=0;retries<=0;slower<=0;
            measure_epoch_valid<=0;measure_detector_valid<=0;measure_balanced<=0;measure_fastest<=0;
            measure_period_short<=0;measure_period_long<=0;failure_code<=0;
        end else if(!allowed)begin
            state<=IDLE;measure_epoch_valid<=0;measure_detector_valid<=0;
            measure_balanced<=0;measure_period_short<=0;measure_period_long<=0;
        end else case(state)
            IDLE:begin
                period_mode<=!separated_mode;pair_index<=0;swap<=0;positive_offset<=0;
                vote_count<=0;ones<=0;retries<=0;slower<=0;balanced<=1;
                measure_epoch_valid<=0;measure_detector_valid<=0;measure_balanced<=0;
                measure_period_short<=0;measure_period_long<=0;failure_code<=0;
                sequence_id<=sequence_id+1'b1;
                if(!MODEL_ADMITTED || VOTES<3 || VOTES%2==0 || VOTES>32767 || MAX_RETRIES<0 || MAX_RETRIES>65534)
                    reject(4'd8);
                else state<=ROUTE;
            end
            ROUTE:if(trial_routes_applied && trial_routes_sequence==sequence_id)state<=ISSUE;
            ISSUE:if(trial_request_ready)state<=WAIT_RESULT;
            WAIT_RESULT:if(trial_result_valid)begin
                if(trial_result_sequence!=sequence_id)reject(4'd4);
                else if(!trial_epoch_valid || !trial_detector_valid || !(trial_reference_first ^ trial_feedback_first))begin
                    // Retry only an explicitly unresolved arbiter decision.
                    // Missing/duplicate tags, timeout and admission faults fail.
                    if(trial_failure_code==5 && !trial_detector_valid &&
                       !trial_reference_first && !trial_feedback_first && retries<MAX_RETRIES)begin
                        retries<=retries+1'b1;next_trial;
                    end else reject(trial_failure_code==0 ? 4'd5 : trial_failure_code);
                end else if(trial_failure_code!=0)reject(trial_failure_code);
                else if(vote_count!=VOTES-1)begin
                    vote_count<=vote_count+1'b1;ones<=ones+(trial_reference_first ? 16'd1 : 16'd0);next_trial;
                end else begin
                    vote_count<=0;ones<=0;retries<=0;
                    if(!swap)begin swap0_vote<=majority;swap<=1;next_trial;end
                    else if(swap0_vote!=majority)reject(4'd5);
                    else if(!positive_offset)begin
                        negative_vote<=majority;positive_offset<=1;swap<=0;next_trial;
                    end else if(negative_vote && !majority)reject(4'd5);
                    else if(period_mode)begin
                        measure_epoch_valid<=1;measure_detector_valid<=1;
                        measure_period_short<=!negative_vote && !majority;
                        measure_period_long<=negative_vote && majority;state<=REPORT;
                    end else begin
                        next_slower=slower;pair_tied=!negative_vote && majority;
                        if(negative_vote && majority)next_slower[pair_b(pair_index)]=1;
                        else if(!negative_vote && !majority)next_slower[pair_a(pair_index)]=1;
                        slower<=next_slower;balanced<=balanced && pair_tied;
                        if(pair_index==5)begin
                            if(next_slower==4'b1111)reject(4'd5);
                            else begin
                                measure_epoch_valid<=1;measure_detector_valid<=1;
                                measure_balanced<=balanced && pair_tied;
                                measure_fastest<=!next_slower[0] ? 0 : !next_slower[1] ? 1 : !next_slower[2] ? 2 : 3;
                                state<=REPORT;
                            end
                        end else begin
                            pair_index<=pair_index+1'b1;swap<=0;positive_offset<=0;next_trial;
                        end
                    end
                end
            end
            REPORT:state<=WAIT_RELEASE;
            WAIT_RELEASE:begin end
            default:reject(4'd4);
        endcase
endmodule
`default_nettype wire
