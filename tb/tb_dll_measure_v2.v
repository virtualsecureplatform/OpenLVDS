// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Abstract transaction oracle ONLY: physical offsets, detector timing and
// delay tables remain unadmitted. The real calibration FSM is exercised here.
module tb_dll_measure_v2;
    parameter INTEGRATED=0,ADMITTED=1;
    reg clk=0,reset_n=1,enable=1,present=1,train=0,manual_request=0,manual_separated=1;
    always #20 clk=~clk;
    wire cal_request,cal_separated,cal_busy,locked,cal_fail;
    wire [3:0] cal_failure;
    wire [15:0] codes;
    wire request=INTEGRATED ? cal_request : manual_request;
    wire separated=INTEGRATED ? cal_separated : manual_separated;
    wire valid,epoch_ok,detector_ok,balanced,short_period,long_period;
    wire [1:0] fastest;
    wire [3:0] failure;
    wire cancel,trial_request,trial_ready,trial_next,trial_swap,trial_positive,trial_result_ready;
    wire [1:0] section_a,section_b;
    wire [15:0] sequence_id;
    reg bad_route_sequence=0;
    wire [15:0] route_sequence=bad_route_sequence ? sequence_id-1'b1 : sequence_id;
    reg result_valid=0,result_epoch=0,result_detector=0,result_reference=0,result_feedback=0;
    reg [15:0] result_sequence=0;
    reg [3:0] result_failure=0;
    openlvds_dll_measure_v2 #(.MODEL_ADMITTED(ADMITTED)) engine(
        .mgmt_clk_25(clk),.reset_n(reset_n),.enable(enable),.clock_present(present),
        .measure_request(request),.separated_mode(separated),.measure_valid(valid),
        .measure_epoch_valid(epoch_ok),.measure_detector_valid(detector_ok),.measure_balanced(balanced),
        .measure_fastest(fastest),.measure_period_short(short_period),.measure_period_long(long_period),
        .failure_code(failure),.trial_cancel(cancel),.trial_request_valid(trial_request),
        .trial_request_ready(trial_ready),.trial_routes_applied(1'b1),.trial_routes_sequence(route_sequence),
        .trial_next_period(trial_next),.trial_swap(trial_swap),.trial_positive_offset(trial_positive),
        .trial_section_a(section_a),.trial_section_b(section_b),.trial_sequence(sequence_id),
        .trial_result_valid(result_valid),.trial_result_ready(trial_result_ready),
        .trial_result_sequence(result_sequence),.trial_epoch_valid(result_epoch),.trial_detector_valid(result_detector),
        .trial_reference_first(result_reference),.trial_feedback_first(result_feedback),.trial_failure_code(result_failure)
    );
    openlvds_dll_calibrate_v2 #(.CODE_WIDTH(4),.LAST_CODE(15)) calibration(
        .mgmt_clk_25(clk),.reset_n(reset_n),.enable(enable && INTEGRATED),.train_req(train),.clock_present(present),
        .codes_applied(1'b1),.measure_valid(valid),.measure_epoch_valid(epoch_ok),.measure_balanced(balanced),
        .measure_fastest(fastest),.measure_period_short(short_period),.measure_period_long(long_period),
        .measure_detector_valid(detector_ok),.measure_request(cal_request),.separated_mode(cal_separated),
        .codes(codes),.cal_busy(cal_busy),.locked(locked),.cal_fail(cal_fail),.failure_code(cal_failure)
    );
    integer delays[0:3];
    integer accepted=0,pending=0,countdown=0,fault=0,unresolved_remaining=0;
    integer delta,total,i,code_index,eligible_delay,min_delay,max_delay;
    reg decision;
    assign trial_ready=!pending && !result_valid;
    always @(posedge clk)begin
        if(!reset_n || cancel)begin pending=0;result_valid<=0;end
        else if(trial_request && trial_ready)begin
            accepted=accepted+1;pending=1;countdown=2;
            total=0;
            for(i=0;i<4;i=i+1)begin
                if(INTEGRATED)begin code_index=(codes>>(4*i))&15;delays[i]=600+8*i+8*code_index;end
                total=total+delays[i];
            end
            delta=(trial_next ? total-2500 : delays[section_b]-delays[section_a])+(trial_positive ? 20 : -20);
            decision=delta>=0;
            if(fault==3 && trial_swap)decision=!decision;
            if(fault==4)decision=!trial_positive;
            if(fault==8 && accepted%3==0)decision=!decision;
            result_sequence<=sequence_id+(fault==2 ? 1 : 0);
            result_epoch<=1;result_detector<=1;result_reference<=decision;result_feedback<=!decision;result_failure<=0;
            if(unresolved_remaining>0)begin
                unresolved_remaining=unresolved_remaining-1;
                result_epoch<=0;result_detector<=0;result_reference<=0;result_feedback<=0;result_failure<=5;
            end
            if(fault==5)begin result_epoch<=0;result_detector<=0;result_reference<=0;result_feedback<=0;result_failure<=4;end
            if(fault==6)begin result_reference<=1;result_feedback<=1;end
        end else if(pending)begin
            if(countdown==0)begin pending=0;result_valid<=1;end
            else countdown=countdown-1;
        end else if(result_valid && trial_result_ready)result_valid<=0;
    end
    task measurement;
        input separate,expect_balanced;
        input [1:0] expect_fastest;
        input expect_short,expect_long;
        input [3:0] expect_failure;
        integer before_count,at_report;
        begin
            @(negedge clk);manual_request=0;repeat(3)@(negedge clk);
            before_count=accepted;manual_separated=separate;manual_request=1;
            if(bad_route_sequence)begin
                repeat(12)@(negedge clk);
                if(accepted!=before_count)$fatal(1,"Stale route acknowledgement launched a trial");
                bad_route_sequence=0;
            end
            wait(valid);#0.001;
            if(failure!=expect_failure)$fatal(1,"Wrong measurement failure %d expected %d",failure,expect_failure);
            if(expect_failure==0)begin
                if(!epoch_ok || !detector_ok || balanced!=expect_balanced ||
                   (separate && fastest!=expect_fastest) || short_period!=expect_short || long_period!=expect_long)
                    $fatal(1,"Incorrect bracket, eligible minimum or period result %b %d %b %b",balanced,fastest,short_period,long_period);
            end else if(epoch_ok || detector_ok || balanced || short_period || long_period)$fatal(1,"Failed trial admitted lock evidence");
            at_report=accepted;repeat(5)@(negedge clk);
            if(accepted!=at_report || valid)$fatal(1,"Level request repeated a completed measurement");
            manual_request=0;
        end
    endtask
    reg [15:0] frozen_codes;
    integer before_count;
    initial begin
        delays[0]=600;delays[1]=610;delays[2]=615;delays[3]=605;
        #0.001;reset_n=0;#10;reset_n=1;
        if(!ADMITTED)begin
            measurement(1,0,0,0,0,8);
            if(accepted!=0)$fatal(1,"Unadmitted engine emitted a trial");
            $display("PASS v2 unadmitted DLL measurement remains closed");$finish;
        end
        if(INTEGRATED)begin
            @(negedge clk);train=1;@(negedge clk);train=0;
            wait(locked || cal_fail);#0.001;
            if(cal_fail)$fatal(1,"Integrated calibration failed %d",cal_failure);
            total=0;min_delay=100000;max_delay=0;
            for(i=0;i<4;i=i+1)begin
                code_index=(codes>>(4*i))&15;eligible_delay=600+8*i+8*code_index;
                total=total+eligible_delay;
                if(eligible_delay<min_delay)min_delay=eligible_delay;
                if(eligible_delay>max_delay)max_delay=eligible_delay;
            end
            if(total<2480 || total>2520 || max_delay-min_delay>20 || accepted<64*84)
                $fatal(1,"False integrated lock period=%d spread=%d trials=%d",total,max_delay-min_delay,accepted);
            frozen_codes=codes;repeat(100)@(negedge clk);
            if(!locked || codes!=frozen_codes || request)$fatal(1,"Payload codes did not freeze");
            present=0;@(posedge clk);#0.001;
            if(locked || !cal_fail || cal_failure!=1 || !cancel)$fatal(1,"Locked clock loss not invalidated");
            $display("PASS v2 measurement engine drives real calibration FSM through code updates and 64 confirmations");$finish;
        end
        bad_route_sequence=1;measurement(1,1,0,0,0,0);
        delays[0]=600;delays[1]=615;delays[2]=630;delays[3]=645;
        measurement(1,0,0,0,0,0); // Adjacent pairs alone would miss full spread.
        delays[0]=645;delays[1]=630;delays[2]=615;delays[3]=600;
        measurement(1,0,2,0,0,0); // Section 2 is within the bracket of minimum 3.
        for(i=0;i<4;i=i+1)delays[i]=600;
        measurement(0,0,0,1,0,0);
        for(i=0;i<4;i=i+1)delays[i]=625;
        measurement(0,0,0,0,0,0);
        for(i=0;i<4;i=i+1)delays[i]=650;
        measurement(0,0,0,0,1,0);
        for(i=0;i<4;i=i+1)delays[i]=1250;
        measurement(0,0,0,0,1,0); // Two periods must remain long.
        for(i=0;i<4;i=i+1)delays[i]=625;
        unresolved_remaining=1;before_count=accepted;measurement(1,1,0,0,0,0);
        if(accepted-before_count!=73)$fatal(1,"Unresolved vote was counted or not retried");
        unresolved_remaining=5;before_count=accepted;measurement(1,0,0,0,0,5);
        if(accepted-before_count!=4)$fatal(1,"Retry bound was not enforced");unresolved_remaining=0;
        fault=2;measurement(1,0,0,0,0,4);
        fault=3;measurement(1,0,0,0,0,5);
        fault=4;measurement(1,0,0,0,0,5);
        fault=5;measurement(1,0,0,0,0,4);
        fault=6;measurement(1,0,0,0,0,5);
        fault=8;measurement(1,1,0,0,0,0);fault=0;
        $display("PASS v2 six-pair balancing, bracket votes, swapped-input agreement, tagged routes and bounded faults");$finish;
    end
    initial begin #30000000;$fatal(1,"DLL measurement watchdog engine=%d calibration=%d",engine.state,calibration.state);end
endmodule
